from typing import Any

import pytest
from confluent_kafka import KafkaException

from customer360.messaging.config import KafkaSettings
from customer360.messaging.producer import CustomerEventProducer
from customer360.messaging.schemas import (
    CustomerEvent,
    CustomerEventType,
    CustomerProfilePayload,
)


class FakeProducer:
    def __init__(
        self,
        flush_result: int = 0,
        produce_error: Exception | None = None,
    ) -> None:
        self.flush_result = flush_result
        self.produce_error = produce_error
        self.messages: list[dict[str, Any]] = []
        self.poll_calls: list[float] = []
        self.flush_calls: list[float] = []

    def produce(self, **kwargs: Any) -> None:
        if self.produce_error is not None:
            raise self.produce_error

        self.messages.append(kwargs)

    def poll(self, timeout: float) -> None:
        self.poll_calls.append(timeout)

    def flush(self, timeout: float) -> int:
        self.flush_calls.append(timeout)
        return self.flush_result


@pytest.fixture
def settings() -> KafkaSettings:
    return KafkaSettings(
        bootstrap_servers="localhost:9092",
        topic="customer360.customer-events.v1",
        consumer_group="customer360-profile-consumer",
        auto_offset_reset="earliest",
    )


@pytest.fixture
def event() -> CustomerEvent:
    return CustomerEvent(
        event_type=CustomerEventType.CREATED,
        payload=CustomerProfilePayload(
            customer_id="1001",
            first_name="John",
            last_name="Smith",
            email="john.smith@example.com",
            city="Atlanta",
            state="GA",
            transaction_count=3,
            total_spend=240.0,
            average_transaction_value=80.0,
        ),
    )


def test_publish_serializes_and_queues_event(
    settings: KafkaSettings,
    event: CustomerEvent,
) -> None:
    fake_producer = FakeProducer()
    producer = CustomerEventProducer(
        settings=settings,
        producer=fake_producer,
    )

    producer.publish(event)

    assert len(fake_producer.messages) == 1

    message = fake_producer.messages[0]

    assert message["topic"] == settings.topic
    assert message["key"] == b"1001"
    assert CustomerEvent.model_validate_json(message["value"]) == event
    assert callable(message["on_delivery"])
    assert fake_producer.poll_calls == [0]


def test_flush_succeeds_when_all_messages_are_delivered(
    settings: KafkaSettings,
) -> None:
    fake_producer = FakeProducer(flush_result=0)
    producer = CustomerEventProducer(
        settings=settings,
        producer=fake_producer,
    )

    producer.flush(timeout=5.0)

    assert fake_producer.flush_calls == [5.0]


def test_flush_raises_when_messages_remain(
    settings: KafkaSettings,
) -> None:
    fake_producer = FakeProducer(flush_result=2)
    producer = CustomerEventProducer(
        settings=settings,
        producer=fake_producer,
    )

    with pytest.raises(
        KafkaException,
        match=r"2 Kafka message\(s\) were not delivered",
    ):
        producer.flush(timeout=5.0)


def test_publish_converts_buffer_error_to_kafka_exception(
    settings: KafkaSettings,
    event: CustomerEvent,
) -> None:
    fake_producer = FakeProducer(
        produce_error=BufferError("producer queue full")
    )
    producer = CustomerEventProducer(
        settings=settings,
        producer=fake_producer,
    )

    with pytest.raises(KafkaException, match="producer queue full"):
        producer.publish(event)


def test_close_flushes_pending_messages(
    settings: KafkaSettings,
) -> None:
    fake_producer = FakeProducer()
    producer = CustomerEventProducer(
        settings=settings,
        producer=fake_producer,
    )

    producer.close()

    assert fake_producer.flush_calls == [10.0]