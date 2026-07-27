"""Stateful engine behind the /demo/pipeline Control Center.

pipeline_telemetry.py (the v1.1 passive dashboard) is deliberately a pure
function of wall-clock time -- no mutable state. This module is the
opposite on purpose: Generate/Inject Failure/Retry/Recover/Reset are
actions whose effects must be visible across separate HTTP requests, so
there has to be real state somewhere. `PipelineSimulationEngine` is that
single source of truth -- one thread-safe, in-memory singleton
(`ENGINE`, at the bottom of this file) shared by every visitor to the demo,
the same way a real shared ops dashboard would be.

Nothing in here calls `random`. Event types and customers cycle
deterministically off an internal sequence counter, and per-stage
processing times are fixed illustrative constants -- so the same sequence
of calls always produces the same results, and every method here is
unit-testable with zero FastAPI/DB/Kafka dependency.

When a database session is supplied, generate/inject_failure/retry mirror a
*real* outbox_events row using the existing, already-tested
OutboxRepository.add()/mark_published()/increment_retry() -- no outbox
business logic is duplicated here. That persistence is strictly
best-effort: this engine's in-memory state is always the source of truth
for what the demo shows, so a database outage never breaks the interactive
flow (see reset()/generate_event()'s `session` handling).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from customer360.outbox.repository import OutboxRepository

HISTORY_LIMIT = 200
MAX_RETRIES = 5  # matches OutboxEvent.max_retries's default, so a real
# mirrored row and this engine's own retry_count can never drift.


class PipelineEngineError(RuntimeError):
    """Raised for invalid actions given the engine's current state."""


class EventStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    DLQ = "dlq"


class StepStatus(StrEnum):
    OK = "ok"
    FAILED = "failed"
    PENDING = "pending"


class FailureType(StrEnum):
    CONSUMER_FAILURE = "consumer_failure"
    KAFKA_TIMEOUT = "kafka_timeout"
    DATABASE_TIMEOUT = "database_timeout"
    SERIALIZATION_ERROR = "serialization_error"
    VALIDATION_FAILURE = "validation_failure"


# The "happy path" a generated event travels when nothing fails.
HAPPY_PATH: tuple[str, ...] = ("Producer", "Kafka Topic", "Outbox", "Consumer", "PostgreSQL")

FAILURE_STAGE: dict[FailureType, str] = {
    FailureType.VALIDATION_FAILURE: "Producer",
    FailureType.KAFKA_TIMEOUT: "Kafka Topic",
    FailureType.SERIALIZATION_ERROR: "Outbox",
    FailureType.CONSUMER_FAILURE: "Consumer",
    FailureType.DATABASE_TIMEOUT: "PostgreSQL",
}

EVENT_TYPES: tuple[str, ...] = (
    "Customer Updated",
    "Order Created",
    "Email Changed",
    "Address Changed",
    "Payment Received",
    "Loyalty Points Added",
)

# Fixed, illustrative per-stage processing times in milliseconds -- not
# measured, deterministic by design.
STAGE_PROCESSING_MS: dict[str, float] = {
    "Producer": 6.0,
    "Kafka Topic": 14.0,
    "Outbox": 5.0,
    "Consumer": 22.0,
    "Retry Queue": 9.0,
    "Dead Letter Queue": 4.0,
    "PostgreSQL": 11.0,
}


@dataclass(frozen=True)
class TraceStep:
    stage: str
    status: StepStatus
    processing_time_ms: float
    timestamp: datetime


@dataclass(frozen=True)
class SimulatedEvent:
    event_id: str
    event_type: str
    customer_id: str
    created_at: datetime
    status: EventStatus
    retry_count: int = 0
    failure_type: FailureType | None = None


@dataclass(frozen=True)
class EventTrace:
    event: SimulatedEvent
    steps: list[TraceStep]
    replay: bool = False


@dataclass(frozen=True)
class PipelineState:
    current_event: SimulatedEvent | None
    consumer_healthy: bool
    generated_count: int
    success_count: int
    failed_count: int
    retry_queue_count: int
    dlq_count: int
    has_replayable_event: bool


def _build_steps(
    stage_statuses: list[tuple[str, StepStatus]], start: datetime
) -> list[TraceStep]:
    steps: list[TraceStep] = []
    moment = start
    for stage, status in stage_statuses:
        duration = STAGE_PROCESSING_MS[stage]
        steps.append(
            TraceStep(stage=stage, status=status, processing_time_ms=duration, timestamp=moment)
        )
        moment = moment + timedelta(milliseconds=duration)
    return steps


def _happy_path_steps(start: datetime) -> list[TraceStep]:
    return _build_steps([(stage, StepStatus.OK) for stage in HAPPY_PATH], start)


def _failure_steps(fail_stage: str, start: datetime) -> list[TraceStep]:
    index = HAPPY_PATH.index(fail_stage)
    prior_ok = [(stage, StepStatus.OK) for stage in HAPPY_PATH[:index]]
    statuses = [*prior_ok, (fail_stage, StepStatus.FAILED), ("Retry Queue", StepStatus.PENDING)]
    return _build_steps(statuses, start)


def _resume_steps(fail_stage: str, start: datetime) -> list[TraceStep]:
    index = HAPPY_PATH.index(fail_stage)
    statuses = [("Retry Queue", StepStatus.OK)]
    statuses += [(stage, StepStatus.OK) for stage in HAPPY_PATH[index:]]
    return _build_steps(statuses, start)


def _dlq_steps(start: datetime) -> list[TraceStep]:
    return _build_steps(
        [("Retry Queue", StepStatus.FAILED), ("Dead Letter Queue", StepStatus.OK)], start
    )


def _still_failing_steps(fail_stage: str, start: datetime) -> list[TraceStep]:
    return _build_steps([("Retry Queue", StepStatus.FAILED), (fail_stage, StepStatus.FAILED)], start)


class PipelineSimulationEngine:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sequence = 0
        self._current_event: SimulatedEvent | None = None
        self._last_trace: EventTrace | None = None
        self._history: list[SimulatedEvent] = []
        self._consumer_healthy = True
        self._demo_outbox_event_ids: list[str] = []

    # -- state ---------------------------------------------------------

    def get_state(self) -> PipelineState:
        with self._lock:
            return self._state_locked()

    def _state_locked(self) -> PipelineState:
        return PipelineState(
            current_event=self._current_event,
            consumer_healthy=self._consumer_healthy,
            generated_count=len(self._history),
            success_count=sum(1 for e in self._history if e.status == EventStatus.SUCCESS),
            failed_count=sum(
                1 for e in self._history if e.status in (EventStatus.FAILED, EventStatus.DLQ)
            ),
            retry_queue_count=sum(1 for e in self._history if e.status == EventStatus.FAILED),
            dlq_count=sum(1 for e in self._history if e.status == EventStatus.DLQ),
            has_replayable_event=self._last_trace is not None,
        )

    # -- actions ---------------------------------------------------------

    def generate_event(
        self,
        session: Session | None = None,
        real_customer_ids: tuple[str, ...] = (),
    ) -> EventTrace:
        with self._lock:
            trace = self._generate_locked(real_customer_ids)
        self._persist_generated(session, trace.event)
        return trace

    def _generate_locked(self, real_customer_ids: tuple[str, ...]) -> EventTrace:
        self._sequence += 1
        seq = self._sequence
        now = datetime.now(UTC)

        event = SimulatedEvent(
            event_id=f"SIM-EVT-{seq:06d}",
            event_type=EVENT_TYPES[seq % len(EVENT_TYPES)],
            customer_id=(
                real_customer_ids[seq % len(real_customer_ids)]
                if real_customer_ids
                else f"SIM-{seq:04d}"
            ),
            created_at=now,
            status=EventStatus.SUCCESS,
        )

        trace = EventTrace(event=event, steps=_happy_path_steps(now))

        self._current_event = event
        self._history.append(event)
        if len(self._history) > HISTORY_LIMIT:
            self._history.pop(0)
        self._last_trace = trace

        return trace

    def replay_last_event(self) -> EventTrace:
        with self._lock:
            if self._last_trace is None:
                raise PipelineEngineError("No event has been generated yet.")
            return replace(self._last_trace, replay=True)

    def inject_failure(
        self,
        failure_type: FailureType,
        session: Session | None = None,
        real_customer_ids: tuple[str, ...] = (),
    ) -> EventTrace:
        # Every failure type is modeled as ultimately manifesting as
        # consumer distress for retry-resolution purposes: this engine has
        # exactly one recovery lever (Recover Consumer), so that's the one
        # condition retry_failed_event() checks, regardless of which of the
        # 5 failure types was injected. See module docstring / README for
        # the reasoning.
        with self._lock:
            if self._current_event is None or self._current_event.status == EventStatus.DLQ:
                self._generate_locked(real_customer_ids)

            event = self._current_event
            assert event is not None  # generated immediately above if it was None

            fail_stage = FAILURE_STAGE[failure_type]
            now = datetime.now(UTC)
            retry_count = event.retry_count if event.status == EventStatus.FAILED else 1
            updated_event = replace(
                event,
                status=EventStatus.FAILED,
                failure_type=failure_type,
                retry_count=retry_count,
            )
            trace = EventTrace(event=updated_event, steps=_failure_steps(fail_stage, now))

            self._current_event = updated_event
            self._history[-1] = updated_event
            self._last_trace = trace
            self._consumer_healthy = False

        self._persist_failure(session, updated_event)
        return trace

    def retry_failed_event(self, session: Session | None = None) -> EventTrace:
        with self._lock:
            event = self._current_event
            if event is None or event.status != EventStatus.FAILED:
                raise PipelineEngineError("There is no failed event to retry.")

            assert event.failure_type is not None
            fail_stage = FAILURE_STAGE[event.failure_type]
            now = datetime.now(UTC)
            new_retry_count = event.retry_count + 1

            if self._consumer_healthy:
                updated_event = replace(
                    event, status=EventStatus.SUCCESS, retry_count=new_retry_count
                )
                trace = EventTrace(event=updated_event, steps=_resume_steps(fail_stage, now))
            elif new_retry_count >= MAX_RETRIES:
                updated_event = replace(
                    event, status=EventStatus.DLQ, retry_count=new_retry_count
                )
                trace = EventTrace(event=updated_event, steps=_dlq_steps(now))
            else:
                updated_event = replace(
                    event, status=EventStatus.FAILED, retry_count=new_retry_count
                )
                trace = EventTrace(
                    event=updated_event, steps=_still_failing_steps(fail_stage, now)
                )

            self._current_event = updated_event
            self._history[-1] = updated_event
            self._last_trace = trace

        self._persist_retry(session, updated_event)
        return trace

    def recover_consumer(self) -> PipelineState:
        with self._lock:
            self._consumer_healthy = True
            return self._state_locked()

    def reset(self, session: Session | None = None) -> PipelineState:
        with self._lock:
            demo_event_ids = list(self._demo_outbox_event_ids)
            self._sequence = 0
            self._current_event = None
            self._last_trace = None
            self._history = []
            self._consumer_healthy = True
            self._demo_outbox_event_ids = []
            state = self._state_locked()

        if session is not None and demo_event_ids:
            try:
                OutboxRepository(session).delete_by_event_ids(demo_event_ids)
            except SQLAlchemyError:
                session.rollback()

        return state

    # -- best-effort persistence -----------------------------------------
    #
    # Every method below only mirrors this engine's already-decided,
    # in-memory outcome into a real outbox_events row for authenticity. A
    # failure here is swallowed (after rollback) and never raised -- the
    # interactive demo must keep working even if the database is down.

    def _persist_generated(self, session: Session | None, event: SimulatedEvent) -> None:
        if session is None:
            return
        try:
            repository = OutboxRepository(session)
            row = repository.add(
                event_id=event.event_id,
                event_type=event.event_type,
                payload=f'{{"customer_id": "{event.customer_id}"}}',
            )
            if event.status == EventStatus.SUCCESS:
                repository.mark_published(row)
            with self._lock:
                self._demo_outbox_event_ids.append(event.event_id)
        except SQLAlchemyError:
            session.rollback()

    def _persist_failure(self, session: Session | None, event: SimulatedEvent) -> None:
        if session is None:
            return
        try:
            repository = OutboxRepository(session)
            row = repository.get_by_event_id(event.event_id)
            if row is not None:
                repository.increment_retry(row)
        except SQLAlchemyError:
            session.rollback()

    def _persist_retry(self, session: Session | None, event: SimulatedEvent) -> None:
        """event.status is already the post-retry outcome: SUCCESS, FAILED
        (still failing, will need another retry), or DLQ."""

        if session is None:
            return
        try:
            repository = OutboxRepository(session)
            row = repository.get_by_event_id(event.event_id)
            if row is None:
                return
            repository.increment_retry(row)
            if event.status == EventStatus.SUCCESS:
                repository.mark_published(row)
        except SQLAlchemyError:
            session.rollback()


ENGINE = PipelineSimulationEngine()
