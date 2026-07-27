"""Deterministic simulation engine backing the /demo/pipeline dashboard.

Kafka isn't running in production, no standalone consumer worker is
deployed, and the outbox_events table has no live writers (see README ->
Limitations). So most of what /demo/pipeline shows has no live backing.

Everything below is a pure function of a timestamp (and, where real data
exists, real repository counts): the same `now` always produces the same
output, so it's unit-testable without a running Kafka broker, and it evolves
smoothly across real wall-clock time -- via slow sine waves and a
time-bucketed seeded Random, never `random` reseeded per call -- instead of
being unrelated noise on every request. Values are kept internally
consistent by construction (e.g. successful + failed == processed, retry
queue and DLQ depth are always subsets of failed events) rather than drawn
independently. The frontend labels every one of these numbers "Simulated
Pipeline Telemetry"; nothing here is ever presented as production metrics.

The one exception is the PostgreSQL pipeline stage and the Database/API
service cards, which reflect real repository counts and real DB
reachability -- the one part of this page that is genuinely live.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

EPOCH = datetime(2026, 1, 1, tzinfo=UTC)
CYCLE_SECONDS = 3600.0  # KPIs roll over hourly, like a "last hour" tile.


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class KpiMetrics:
    messages_processed: int
    successful_events: int
    failed_events: int
    retry_queue: int
    dlq_messages: int
    avg_processing_time_ms: float
    events_per_sec: float
    consumer_lag: int


@dataclass(frozen=True)
class StageMetric:
    name: str
    count: int
    status: HealthStatus


@dataclass(frozen=True)
class PipelineSummary:
    generated_at: datetime
    kpis: KpiMetrics
    stages: list[StageMetric]


@dataclass(frozen=True)
class ServiceHealth:
    name: str
    status: HealthStatus
    latency_ms: float
    last_heartbeat: datetime


@dataclass(frozen=True)
class EventStreamEntry:
    timestamp: datetime
    event_type: str
    status: HealthStatus
    detail: str


@dataclass(frozen=True)
class ChartSeries:
    label: str
    categories: list[str]
    values: list[float]


@dataclass(frozen=True)
class PipelineCharts:
    messages_per_minute: ChartSeries
    retries_over_time: ChartSeries
    dlq_trend: ChartSeries
    success_series: ChartSeries
    failure_series: ChartSeries
    latency_ms: ChartSeries
    top_event_types: ChartSeries


@dataclass(frozen=True)
class CustomerFlowStep:
    label: str
    timestamp: datetime
    status: HealthStatus


CUSTOMER_FLOW_STEPS: tuple[str, ...] = (
    "Profile Created",
    "Events Produced",
    "Kafka Published",
    "Consumer Processed",
    "Stored",
    "Audit Logged",
)

# (label, status, relative weight) -- weights don't need to sum to 1.
EVENT_TEMPLATES: tuple[tuple[str, HealthStatus, float], ...] = (
    ("Customer Updated", HealthStatus.HEALTHY, 0.28),
    ("Customer Created", HealthStatus.HEALTHY, 0.12),
    ("Kafka Publish", HealthStatus.HEALTHY, 0.16),
    ("Consumer Commit", HealthStatus.HEALTHY, 0.18),
    ("Outbox Drained", HealthStatus.HEALTHY, 0.06),
    ("Retry Attempt", HealthStatus.WARNING, 0.12),
    ("DLQ Message", HealthStatus.CRITICAL, 0.05),
    ("Audit Logged", HealthStatus.HEALTHY, 0.03),
)


def _as_utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _elapsed_seconds(now: datetime) -> float:
    return max((_as_utc(now) - EPOCH).total_seconds(), 0.0)


def _cycle_progress(now: datetime) -> float:
    """Seconds into the current hour-long simulation cycle, in [0, 3600)."""

    return _elapsed_seconds(now) % CYCLE_SECONDS


def _bucket_rng(now: datetime, bucket_seconds: int, salt: str) -> random.Random:
    bucket = int(_elapsed_seconds(now) // bucket_seconds)
    return random.Random(f"{salt}:{bucket}")


def _status_from_thresholds(
    value: float, *, warning: float, critical: float
) -> HealthStatus:
    if value >= critical:
        return HealthStatus.CRITICAL
    if value >= warning:
        return HealthStatus.WARNING
    return HealthStatus.HEALTHY


def _kpi_curve_at(
    seconds_into_cycle: float, base_rate: float, rng: random.Random
) -> KpiMetrics:
    wave = 1 + 0.15 * math.sin(seconds_into_cycle / 300.0)
    jitter = 1 + rng.uniform(-0.04, 0.04)

    messages_processed = max(0, int(seconds_into_cycle * base_rate * wave))
    events_per_sec = round(max(0.0, base_rate * wave * jitter), 2)

    failure_rate = 0.015 + 0.01 * (1 + math.sin(seconds_into_cycle / 400.0)) / 2
    failed_events = int(messages_processed * failure_rate)
    successful_events = messages_processed - failed_events

    retry_wave = (1 + math.sin(seconds_into_cycle / 90.0)) / 2
    retry_queue = min(
        failed_events,
        max(0, int(4 + 10 * retry_wave + rng.uniform(-1, 1))),
    )
    dlq_messages = min(failed_events, max(0, int(failed_events * 0.05)))

    avg_processing_time_ms = round(
        max(5.0, 55 + 18 * math.sin(seconds_into_cycle / 120.0) + rng.uniform(-2, 2)),
        1,
    )
    consumer_lag = max(0, int(retry_queue * 1.3 + rng.uniform(0, 4)))

    return KpiMetrics(
        messages_processed=messages_processed,
        successful_events=successful_events,
        failed_events=failed_events,
        retry_queue=retry_queue,
        dlq_messages=dlq_messages,
        avg_processing_time_ms=avg_processing_time_ms,
        events_per_sec=events_per_sec,
        consumer_lag=consumer_lag,
    )


def _base_rate(real_customer_count: int) -> float:
    # Nudged by real seeded data so the simulation isn't fully divorced from
    # what's actually in the database, without letting a huge customer count
    # produce an implausible throughput.
    return 3.0 + 0.08 * min(real_customer_count, 500)


def compute_kpis(now: datetime, real_customer_count: int) -> KpiMetrics:
    seconds_into_cycle = _cycle_progress(now)
    rng = _bucket_rng(now, 5, "kpi")
    return _kpi_curve_at(seconds_into_cycle, _base_rate(real_customer_count), rng)


def build_summary(
    now: datetime,
    *,
    real_customer_count: int,
    real_outbox_pending: int,
    db_reachable: bool,
) -> PipelineSummary:
    kpis = compute_kpis(now, real_customer_count)

    kafka_topic_count = int(kpis.messages_processed * 0.995)
    outbox_count = real_outbox_pending if real_outbox_pending > 0 else kpis.retry_queue // 2

    stages = [
        StageMetric("Producer", kpis.messages_processed, HealthStatus.HEALTHY),
        StageMetric(
            "Kafka Topic",
            kafka_topic_count,
            _status_from_thresholds(kpis.consumer_lag, warning=15, critical=30),
        ),
        StageMetric(
            "Outbox",
            outbox_count,
            _status_from_thresholds(outbox_count, warning=10, critical=25),
        ),
        StageMetric(
            "Consumer",
            kpis.successful_events,
            _status_from_thresholds(kpis.consumer_lag, warning=15, critical=30),
        ),
        StageMetric(
            "Retry Queue",
            kpis.retry_queue,
            _status_from_thresholds(kpis.retry_queue, warning=10, critical=20),
        ),
        StageMetric(
            "Dead Letter Queue",
            kpis.dlq_messages,
            _status_from_thresholds(kpis.dlq_messages, warning=3, critical=8),
        ),
        StageMetric(
            "PostgreSQL",
            real_customer_count,
            HealthStatus.HEALTHY if db_reachable else HealthStatus.CRITICAL,
        ),
    ]

    return PipelineSummary(generated_at=_as_utc(now), kpis=kpis, stages=stages)


def _weighted_choice(
    rng: random.Random, templates: tuple[tuple[str, HealthStatus, float], ...]
) -> tuple[str, HealthStatus]:
    total = sum(weight for _, _, weight in templates)
    roll = rng.uniform(0, total)
    running = 0.0
    for label, status, weight in templates:
        running += weight
        if roll <= running:
            return label, status
    last_label, last_status, _ = templates[-1]
    return last_label, last_status


def build_event_stream(
    now: datetime,
    *,
    count: int = 12,
    interval_seconds: int = 3,
    sample_customer_ids: tuple[str, ...] = (),
) -> list[EventStreamEntry]:
    """Newest-first rolling window of illustrative pipeline events.

    Each slot's content is seeded by its own bucketed timestamp, so it's
    stable within `interval_seconds` (repeated polls show the same entries)
    and a "new" one appears once the bucket rolls over -- giving a live-feed
    feel without server-side mutable state.
    """

    entries: list[EventStreamEntry] = []
    for i in range(count):
        slot_time = now - timedelta(seconds=interval_seconds * i)
        rng = _bucket_rng(slot_time, interval_seconds, "event")
        label, status = _weighted_choice(rng, EVENT_TEMPLATES)

        detail = label
        if sample_customer_ids and rng.random() < 0.6:
            customer_id = sample_customer_ids[rng.randrange(len(sample_customer_ids))]
            detail = f"{label} — {customer_id}"

        entries.append(
            EventStreamEntry(
                timestamp=_as_utc(slot_time),
                event_type=label,
                status=status,
                detail=detail,
            )
        )

    return entries


def build_service_health(
    now: datetime, *, db_reachable: bool, kpis: KpiMetrics
) -> list[ServiceHealth]:
    rng = _bucket_rng(now, 10, "services")
    moment = _as_utc(now)

    def service(name: str, status: HealthStatus, base_latency_ms: float) -> ServiceHealth:
        latency = max(1.0, base_latency_ms + rng.uniform(-3, 3))
        return ServiceHealth(
            name=name,
            status=status,
            latency_ms=round(latency, 1),
            last_heartbeat=moment,
        )

    kafka_status = _status_from_thresholds(kpis.consumer_lag, warning=15, critical=30)
    outbox_status = _status_from_thresholds(kpis.retry_queue, warning=10, critical=20)

    return [
        service("API", HealthStatus.HEALTHY, 8.0),
        service(
            "Database",
            HealthStatus.HEALTHY if db_reachable else HealthStatus.CRITICAL,
            4.0 if db_reachable else 250.0,
        ),
        service("Kafka", kafka_status, 12.0),
        service("Consumer", kafka_status, 18.0),
        service("Outbox", outbox_status, 6.0),
        service("Scheduler", HealthStatus.HEALTHY, 3.0),
    ]


def build_charts(now: datetime, *, real_customer_count: int, kpis: KpiMetrics) -> PipelineCharts:
    base_rate = _base_rate(real_customer_count)

    categories: list[str] = []
    messages_per_minute: list[float] = []
    retries_over_time: list[float] = []
    dlq_trend: list[float] = []
    success_series: list[float] = []
    failure_series: list[float] = []
    latency_ms: list[float] = []

    for minutes_ago in range(29, -1, -1):
        sample_time = now - timedelta(minutes=minutes_ago)
        seconds_into_cycle = _cycle_progress(sample_time)
        rng = _bucket_rng(sample_time, 60, "chart")
        sample = _kpi_curve_at(seconds_into_cycle, base_rate, rng)

        categories.append(_as_utc(sample_time).strftime("%H:%M"))
        messages_per_minute.append(round(sample.events_per_sec * 60, 1))
        retries_over_time.append(float(sample.retry_queue))
        dlq_trend.append(float(sample.dlq_messages))
        success_series.append(float(sample.successful_events))
        failure_series.append(float(sample.failed_events))
        latency_ms.append(sample.avg_processing_time_ms)

    event_type_labels = [label for label, _, _ in EVENT_TEMPLATES]
    total_weight = sum(weight for _, _, weight in EVENT_TEMPLATES)
    event_type_counts = [
        round(weight / total_weight * kpis.messages_processed, 0)
        for _, _, weight in EVENT_TEMPLATES
    ]

    return PipelineCharts(
        messages_per_minute=ChartSeries("Messages / min", categories, messages_per_minute),
        retries_over_time=ChartSeries("Retry queue depth", categories, retries_over_time),
        dlq_trend=ChartSeries("DLQ depth", categories, dlq_trend),
        success_series=ChartSeries("Successful events", categories, success_series),
        failure_series=ChartSeries("Failed events", categories, failure_series),
        latency_ms=ChartSeries("Avg processing time (ms)", categories, latency_ms),
        top_event_types=ChartSeries("Top event types", event_type_labels, event_type_counts),
    )


def build_customer_flow(customer_id: str, created_at: datetime) -> list[CustomerFlowStep]:
    """Illustrative per-customer event flow, anchored to the real created_at."""

    rng = random.Random(f"flow:{customer_id}")
    cursor = _as_utc(created_at)
    steps: list[CustomerFlowStep] = []

    for index, label in enumerate(CUSTOMER_FLOW_STEPS):
        if index > 0:
            cursor = cursor + timedelta(
                milliseconds=rng.randint(120, 900) + index * 150
            )
        steps.append(CustomerFlowStep(label=label, timestamp=cursor, status=HealthStatus.HEALTHY))

    return steps
