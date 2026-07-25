from __future__ import annotations

import time
from uuid import uuid4

import pytest

from customer360.messaging.config import KafkaSettings
from customer360.messaging.consumer import CustomerEventConsumer
from customer360.messaging.producer import CustomerEventProducer
from customer360.messaging.schemas import (
    CustomerEvent,
    CustomerEventType,
    CustomerProfilePayload,
)


@pytest.mark.integration
def test_kafka_event_round_trip() -> None:
    unique_id = uuid4().hex

    settings = KafkaSettings(
        bootstrap_servers="localhost:9092",
        topic="customer360.customer-events.v1",
        consumer_group=f"customer360-integration-{unique_id}",
        auto_offset_reset="earliest",
    )

    expected = CustomerEvent(
        event_type=CustomerEventType.CREATED,
        source="integration-test",
        payload=CustomerProfilePayload(
            customer_id=f"integration-{unique_id}",
            first_name="Integration",
            last_name="Test",
            email=f"integration-{unique_id}@example.com",
            city="Atlanta",
            state="GA",
            transaction_count=3,
            total_spend=240.0,
            average_transaction_value=80.0,
        ),
    )

    consumer = CustomerEventConsumer(settings=settings)
    producer = CustomerEventProducer(settings=settings)

    try:
        # Allow the consumer group to join and receive its partition assignment
        # before publishing the event.
        time.sleep(2)

        producer.publish(expected)
        producer.flush(timeout=10.0)

        deadline = time.monotonic() + 15.0
        consumed = None
        events = consumer.consume(timeout=1.0)

        while time.monotonic() < deadline:
            candidate = next(events)

            if candidate.event_id == expected.event_id:
                consumed = candidate
                break

        assert consumed == expected
    finally:
        producer.close()
        consumer.close()