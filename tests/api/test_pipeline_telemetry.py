"""Pipeline-metric tests: the deterministic simulation invariants that back
/demo/pipeline. These run without FastAPI, a database, or Kafka -- pure
functions of a timestamp.
"""

from datetime import UTC, datetime

from customer360.api.pipeline_telemetry import (
    CUSTOMER_FLOW_STEPS,
    HealthStatus,
    build_charts,
    build_customer_flow,
    build_event_stream,
    build_service_health,
    build_summary,
    compute_kpis,
)

NOW = datetime(2026, 7, 27, 14, 30, 0, tzinfo=UTC)


def test_compute_kpis_is_deterministic_for_the_same_timestamp():
    first = compute_kpis(NOW, real_customer_count=10)
    second = compute_kpis(NOW, real_customer_count=10)

    assert first == second


def test_compute_kpis_differs_across_customer_counts():
    small = compute_kpis(NOW, real_customer_count=0)
    large = compute_kpis(NOW, real_customer_count=200)

    assert small != large


def test_compute_kpis_successful_and_failed_sum_to_processed():
    kpis = compute_kpis(NOW, real_customer_count=25)

    assert kpis.successful_events + kpis.failed_events == kpis.messages_processed


def test_compute_kpis_retry_queue_and_dlq_are_bounded_by_failed_events():
    for hour_offset in range(0, 24):
        moment = NOW.replace(hour=hour_offset % 24)
        kpis = compute_kpis(moment, real_customer_count=15)

        assert 0 <= kpis.retry_queue <= kpis.failed_events
        assert 0 <= kpis.dlq_messages <= kpis.failed_events


def test_compute_kpis_values_are_never_negative():
    kpis = compute_kpis(NOW, real_customer_count=0)

    assert kpis.messages_processed >= 0
    assert kpis.successful_events >= 0
    assert kpis.failed_events >= 0
    assert kpis.retry_queue >= 0
    assert kpis.dlq_messages >= 0
    assert kpis.avg_processing_time_ms > 0
    assert kpis.events_per_sec >= 0
    assert kpis.consumer_lag >= 0


def test_compute_kpis_resets_near_the_top_of_each_hour():
    top_of_hour = NOW.replace(minute=0, second=0, microsecond=0)
    kpis = compute_kpis(top_of_hour, real_customer_count=10)

    assert kpis.messages_processed < 50


def test_build_summary_has_seven_stages_in_pipeline_order():
    summary = build_summary(
        NOW, real_customer_count=10, real_outbox_pending=0, db_reachable=True
    )

    assert [stage.name for stage in summary.stages] == [
        "Producer",
        "Kafka Topic",
        "Outbox",
        "Consumer",
        "Retry Queue",
        "Dead Letter Queue",
        "PostgreSQL",
    ]


def test_build_summary_postgres_stage_reflects_real_customer_count_exactly():
    summary = build_summary(
        NOW, real_customer_count=42, real_outbox_pending=0, db_reachable=True
    )

    postgres_stage = summary.stages[-1]
    assert postgres_stage.name == "PostgreSQL"
    assert postgres_stage.count == 42
    assert postgres_stage.status == HealthStatus.HEALTHY


def test_build_summary_postgres_stage_is_critical_when_db_unreachable():
    summary = build_summary(
        NOW, real_customer_count=42, real_outbox_pending=0, db_reachable=False
    )

    assert summary.stages[-1].status == HealthStatus.CRITICAL


def test_build_summary_outbox_stage_prefers_real_pending_count():
    summary = build_summary(
        NOW, real_customer_count=10, real_outbox_pending=7, db_reachable=True
    )

    outbox_stage = next(s for s in summary.stages if s.name == "Outbox")
    assert outbox_stage.count == 7


def test_build_summary_producer_count_is_at_least_kafka_topic_count():
    summary = build_summary(
        NOW, real_customer_count=30, real_outbox_pending=0, db_reachable=True
    )

    producer = next(s for s in summary.stages if s.name == "Producer")
    kafka_topic = next(s for s in summary.stages if s.name == "Kafka Topic")
    assert kafka_topic.count <= producer.count


def test_build_event_stream_returns_requested_count_newest_first():
    entries = build_event_stream(NOW, count=12, interval_seconds=3)

    assert len(entries) == 12
    timestamps = [entry.timestamp for entry in entries]
    assert timestamps == sorted(timestamps, reverse=True)


def test_build_event_stream_is_deterministic():
    first = build_event_stream(NOW, count=5)
    second = build_event_stream(NOW, count=5)

    assert first == second


def test_build_event_stream_can_reference_real_customer_ids():
    entries = build_event_stream(
        NOW,
        count=30,
        interval_seconds=1,
        sample_customer_ids=("DEMO-0001", "DEMO-0002"),
    )

    assert any("DEMO-0001" in entry.detail or "DEMO-0002" in entry.detail for entry in entries)


def test_build_service_health_has_six_named_services():
    kpis = compute_kpis(NOW, real_customer_count=10)
    services = build_service_health(NOW, db_reachable=True, kpis=kpis)

    assert [service.name for service in services] == [
        "API",
        "Database",
        "Kafka",
        "Consumer",
        "Outbox",
        "Scheduler",
    ]
    assert all(service.latency_ms > 0 for service in services)


def test_build_service_health_database_reflects_reachability():
    kpis = compute_kpis(NOW, real_customer_count=10)

    healthy = build_service_health(NOW, db_reachable=True, kpis=kpis)
    unhealthy = build_service_health(NOW, db_reachable=False, kpis=kpis)

    database_healthy = next(s for s in healthy if s.name == "Database")
    database_unhealthy = next(s for s in unhealthy if s.name == "Database")

    assert database_healthy.status == HealthStatus.HEALTHY
    assert database_unhealthy.status == HealthStatus.CRITICAL
    assert database_unhealthy.latency_ms > database_healthy.latency_ms


def test_build_charts_series_are_all_thirty_points_long():
    kpis = compute_kpis(NOW, real_customer_count=10)
    charts = build_charts(NOW, real_customer_count=10, kpis=kpis)

    for series in (
        charts.messages_per_minute,
        charts.retries_over_time,
        charts.dlq_trend,
        charts.success_series,
        charts.failure_series,
        charts.latency_ms,
    ):
        assert len(series.categories) == 30
        assert len(series.values) == 30


def test_build_charts_dlq_and_retries_never_exceed_failures_per_point():
    kpis = compute_kpis(NOW, real_customer_count=10)
    charts = build_charts(NOW, real_customer_count=10, kpis=kpis)

    for dlq, retries, failures in zip(
        charts.dlq_trend.values,
        charts.retries_over_time.values,
        charts.failure_series.values,
        strict=True,
    ):
        assert dlq <= failures
        assert retries <= failures


def test_build_charts_top_event_types_matches_event_template_labels():
    kpis = compute_kpis(NOW, real_customer_count=10)
    charts = build_charts(NOW, real_customer_count=10, kpis=kpis)

    assert len(charts.top_event_types.categories) == 8
    assert all(count >= 0 for count in charts.top_event_types.values)


def test_build_charts_is_deterministic():
    kpis = compute_kpis(NOW, real_customer_count=10)

    first = build_charts(NOW, real_customer_count=10, kpis=kpis)
    second = build_charts(NOW, real_customer_count=10, kpis=kpis)

    assert first == second


def test_build_customer_flow_has_six_ordered_steps_starting_at_created_at():
    created_at = datetime(2026, 6, 1, 9, 0, 0, tzinfo=UTC)
    steps = build_customer_flow("DEMO-0001", created_at)

    assert [step.label for step in steps] == list(CUSTOMER_FLOW_STEPS)
    assert steps[0].timestamp == created_at

    timestamps = [step.timestamp for step in steps]
    assert timestamps == sorted(timestamps)
    assert len(set(timestamps)) == len(timestamps)


def test_build_customer_flow_is_deterministic_per_customer():
    created_at = datetime(2026, 6, 1, 9, 0, 0, tzinfo=UTC)

    first = build_customer_flow("DEMO-0002", created_at)
    second = build_customer_flow("DEMO-0002", created_at)

    assert first == second


def test_build_customer_flow_differs_across_customers():
    created_at = datetime(2026, 6, 1, 9, 0, 0, tzinfo=UTC)

    flow_a = build_customer_flow("DEMO-0001", created_at)
    flow_b = build_customer_flow("DEMO-0002", created_at)

    assert flow_a != flow_b
