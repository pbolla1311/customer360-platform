"""Pure, DB-free tests for the interactive /demo/pipeline Control Center
engine. Every test constructs its own PipelineSimulationEngine() instance
(not the module-level ENGINE singleton) so tests can't leak state into each
other -- the module-level ENGINE's own isolation is covered separately in
tests/api/test_main.py, where main.py actually shares it across requests.
"""

import pytest

from customer360.api.pipeline_simulation_engine import (
    HAPPY_PATH,
    MAX_RETRIES,
    EventStatus,
    FailureType,
    PipelineEngineError,
    PipelineSimulationEngine,
    StepStatus,
)


@pytest.fixture
def engine() -> PipelineSimulationEngine:
    return PipelineSimulationEngine()


def test_generate_event_follows_the_happy_path(engine: PipelineSimulationEngine):
    trace = engine.generate_event()

    assert trace.event.status == EventStatus.SUCCESS
    assert [step.stage for step in trace.steps] == list(HAPPY_PATH)
    assert all(step.status == StepStatus.OK for step in trace.steps)


def test_generate_event_cycles_event_types_deterministically(engine: PipelineSimulationEngine):
    first = engine.generate_event().event.event_type
    second = engine.generate_event().event.event_type

    replay_engine = PipelineSimulationEngine()
    replay_first = replay_engine.generate_event().event.event_type
    replay_second = replay_engine.generate_event().event.event_type

    assert (first, second) == (replay_first, replay_second)


def test_generate_event_uses_real_customer_ids_when_provided(engine: PipelineSimulationEngine):
    trace = engine.generate_event(real_customer_ids=("DEMO-0001", "DEMO-0002"))

    assert trace.event.customer_id in {"DEMO-0001", "DEMO-0002"}


def test_generate_event_falls_back_to_synthetic_customer_when_none_seeded(
    engine: PipelineSimulationEngine,
):
    trace = engine.generate_event(real_customer_ids=())

    assert trace.event.customer_id.startswith("SIM-")


def test_generate_event_ids_are_unique_and_increasing(engine: PipelineSimulationEngine):
    ids = [engine.generate_event().event.event_id for _ in range(5)]

    assert len(set(ids)) == 5
    assert ids == sorted(ids)


def test_replay_without_any_prior_event_raises(engine: PipelineSimulationEngine):
    with pytest.raises(PipelineEngineError):
        engine.replay_last_event()


def test_replay_reuses_the_last_event_without_mutating_history(
    engine: PipelineSimulationEngine,
):
    generated = engine.generate_event()

    replayed = engine.replay_last_event()

    assert replayed.event == generated.event
    assert replayed.replay is True
    assert generated.replay is False
    assert engine.get_state().generated_count == 1


def test_inject_failure_auto_generates_when_no_current_event(engine: PipelineSimulationEngine):
    trace = engine.inject_failure(FailureType.CONSUMER_FAILURE)

    assert trace.event.status == EventStatus.FAILED
    assert trace.event.failure_type == FailureType.CONSUMER_FAILURE
    assert engine.get_state().generated_count == 1


def test_inject_failure_marks_the_correct_stage_failed_for_each_failure_type(
    engine: PipelineSimulationEngine,
):
    expected_stage = {
        FailureType.VALIDATION_FAILURE: "Producer",
        FailureType.KAFKA_TIMEOUT: "Kafka Topic",
        FailureType.SERIALIZATION_ERROR: "Outbox",
        FailureType.CONSUMER_FAILURE: "Consumer",
        FailureType.DATABASE_TIMEOUT: "PostgreSQL",
    }

    for failure_type, stage in expected_stage.items():
        fresh_engine = PipelineSimulationEngine()
        trace = fresh_engine.inject_failure(failure_type)

        failed_steps = [step for step in trace.steps if step.status == StepStatus.FAILED]
        assert len(failed_steps) == 1
        assert failed_steps[0].stage == stage
        assert trace.steps[-1].stage == "Retry Queue"
        assert trace.steps[-1].status == StepStatus.PENDING


def test_inject_failure_puts_the_event_in_the_retry_queue(engine: PipelineSimulationEngine):
    engine.inject_failure(FailureType.KAFKA_TIMEOUT)

    state = engine.get_state()
    assert state.retry_queue_count == 1
    assert state.failed_count == 1
    assert state.success_count == 0
    assert state.dlq_count == 0


def test_retry_without_a_failed_event_raises(engine: PipelineSimulationEngine):
    with pytest.raises(PipelineEngineError):
        engine.retry_failed_event()

    engine.generate_event()  # succeeded, not failed
    with pytest.raises(PipelineEngineError):
        engine.retry_failed_event()


def test_retry_succeeds_and_resumes_from_the_failed_stage_once_recovered(
    engine: PipelineSimulationEngine,
):
    engine.inject_failure(FailureType.CONSUMER_FAILURE)
    engine.recover_consumer()

    trace = engine.retry_failed_event()

    assert trace.event.status == EventStatus.SUCCESS
    assert [step.stage for step in trace.steps] == ["Retry Queue", "Consumer", "PostgreSQL"]
    assert all(step.status == StepStatus.OK for step in trace.steps)

    state = engine.get_state()
    assert state.success_count == 1
    assert state.failed_count == 0
    assert state.retry_queue_count == 0


def test_retry_resumes_the_full_happy_path_when_failure_was_at_producer(
    engine: PipelineSimulationEngine,
):
    engine.inject_failure(FailureType.VALIDATION_FAILURE)
    engine.recover_consumer()

    trace = engine.retry_failed_event()

    assert [step.stage for step in trace.steps] == ["Retry Queue", *HAPPY_PATH]


def test_retry_keeps_failing_while_consumer_stays_unhealthy(engine: PipelineSimulationEngine):
    engine.inject_failure(FailureType.CONSUMER_FAILURE)  # retry_count -> 1

    trace = engine.retry_failed_event()  # retry_count -> 2, consumer still unhealthy

    assert trace.event.status == EventStatus.FAILED
    assert trace.event.retry_count == 2
    assert [step.stage for step in trace.steps] == ["Retry Queue", "Consumer"]
    assert all(step.status == StepStatus.FAILED for step in trace.steps)


def test_repeated_retries_eventually_dead_letter_the_event(engine: PipelineSimulationEngine):
    engine.inject_failure(FailureType.DATABASE_TIMEOUT)  # retry_count now 1, unhealthy

    last_trace = None
    for _ in range(MAX_RETRIES):
        last_trace = engine.retry_failed_event()
        if last_trace.event.status == EventStatus.DLQ:
            break

    assert last_trace is not None
    assert last_trace.event.status == EventStatus.DLQ
    assert last_trace.event.retry_count == MAX_RETRIES
    assert [step.stage for step in last_trace.steps] == ["Retry Queue", "Dead Letter Queue"]

    state = engine.get_state()
    assert state.dlq_count == 1
    assert state.retry_queue_count == 0


def test_recovering_then_retrying_resolves_a_still_failing_event(
    engine: PipelineSimulationEngine,
):
    engine.inject_failure(FailureType.CONSUMER_FAILURE)
    engine.retry_failed_event()  # still fails, retry_count -> 2

    engine.recover_consumer()
    trace = engine.retry_failed_event()  # now succeeds

    assert trace.event.status == EventStatus.SUCCESS
    assert trace.event.retry_count == 3
    assert [step.stage for step in trace.steps] == ["Retry Queue", "Consumer", "PostgreSQL"]


def test_retry_after_dlq_raises_because_event_is_terminal(engine: PipelineSimulationEngine):
    engine.inject_failure(FailureType.CONSUMER_FAILURE)
    for _ in range(MAX_RETRIES):
        trace = engine.retry_failed_event()
        if trace.event.status == EventStatus.DLQ:
            break

    with pytest.raises(PipelineEngineError):
        engine.retry_failed_event()


def test_inject_failure_after_dlq_generates_a_fresh_event(engine: PipelineSimulationEngine):
    engine.inject_failure(FailureType.CONSUMER_FAILURE)
    for _ in range(MAX_RETRIES):
        trace = engine.retry_failed_event()
        if trace.event.status == EventStatus.DLQ:
            break

    dlq_event_id = engine.get_state().current_event.event_id

    new_trace = engine.inject_failure(FailureType.KAFKA_TIMEOUT)

    assert new_trace.event.event_id != dlq_event_id
    assert engine.get_state().generated_count == 2


def test_recover_consumer_is_independent_of_the_current_failed_event(
    engine: PipelineSimulationEngine,
):
    engine.inject_failure(FailureType.CONSUMER_FAILURE)

    state = engine.recover_consumer()

    assert state.consumer_healthy is True
    # The failed event itself is untouched by recovery -- it still needs a
    # retry.
    assert state.current_event is not None
    assert state.current_event.status == EventStatus.FAILED


def test_reset_restores_initial_state(engine: PipelineSimulationEngine):
    engine.generate_event()
    engine.inject_failure(FailureType.CONSUMER_FAILURE)

    state = engine.reset()

    assert state.current_event is None
    assert state.generated_count == 0
    assert state.success_count == 0
    assert state.failed_count == 0
    assert state.retry_queue_count == 0
    assert state.dlq_count == 0
    assert state.has_replayable_event is False
    assert state.consumer_healthy is True

    with pytest.raises(PipelineEngineError):
        engine.replay_last_event()


def test_get_state_counts_are_consistent_across_a_mixed_history(
    engine: PipelineSimulationEngine,
):
    engine.generate_event()  # success #1, becomes historical once #2 is current
    engine.generate_event()  # success #2, becomes "current"
    # Failing the current event mutates it in place rather than generating
    # a 3rd event -- inject_failure only auto-generates when there is no
    # current event yet, or the current one is already terminal (DLQ'd).
    engine.inject_failure(FailureType.KAFKA_TIMEOUT)  # #2 becomes failed

    state = engine.get_state()

    assert state.generated_count == 2
    assert state.success_count == 1
    assert state.failed_count == 1
    assert state.retry_queue_count == 1
    assert state.dlq_count == 0
    assert state.success_count + state.failed_count == state.generated_count
    assert state.retry_queue_count <= state.failed_count
    assert state.dlq_count <= state.failed_count


def test_record_customer_update_follows_the_happy_path(engine: PipelineSimulationEngine):
    trace = engine.record_customer_update("CUST-0001", "Address Changed")

    assert trace.event.status == EventStatus.SUCCESS
    assert trace.event.customer_id == "CUST-0001"
    assert trace.event.event_type == "Address Changed"
    assert [step.stage for step in trace.steps] == list(HAPPY_PATH)
    assert all(step.status == StepStatus.OK for step in trace.steps)
    assert trace.replay is False


def test_record_customer_update_becomes_the_current_event(engine: PipelineSimulationEngine):
    trace = engine.record_customer_update("CUST-0001", "Email Changed")

    state = engine.get_state()
    assert state.current_event is not None
    assert state.current_event.event_id == trace.event.event_id
    assert state.generated_count == 1
    assert state.success_count == 1


def test_record_customer_update_event_ids_are_unique_and_increasing(
    engine: PipelineSimulationEngine,
):
    first = engine.record_customer_update("CUST-0001", "Customer Updated")
    second = engine.record_customer_update("CUST-0002", "Email Changed")

    assert first.event.event_id != second.event.event_id


def test_get_trace_history_is_empty_for_a_fresh_engine(engine: PipelineSimulationEngine):
    assert engine.get_trace_history() == []


def test_get_trace_history_orders_most_recent_first(engine: PipelineSimulationEngine):
    first = engine.generate_event()
    second = engine.record_customer_update("CUST-0001", "Customer Updated")

    history = engine.get_trace_history()

    assert [entry.event.event_id for entry in history] == [
        second.event.event_id,
        first.event.event_id,
    ]


def test_get_trace_history_reflects_in_place_mutations(engine: PipelineSimulationEngine):
    engine.generate_event()
    failed_trace = engine.inject_failure(FailureType.CONSUMER_FAILURE)

    history = engine.get_trace_history()

    assert history[0].event.event_id == failed_trace.event.event_id
    assert history[0].event.status == EventStatus.FAILED


def test_get_trace_history_respects_limit(engine: PipelineSimulationEngine):
    for _ in range(5):
        engine.generate_event()

    assert len(engine.get_trace_history(limit=2)) == 2


def test_reset_clears_trace_history(engine: PipelineSimulationEngine):
    engine.generate_event()
    engine.record_customer_update("CUST-0001", "Customer Updated")

    engine.reset()

    assert engine.get_trace_history() == []
