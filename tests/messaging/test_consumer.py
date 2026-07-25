from typing import Any

import pytest

from customer360.messaging.config import KafkaSettings
from customer360.messaging.consumer import CustomerEventConsumer
from customer360.messaging.schemas import (
    CustomerEvent,
    CustomerEventType,
    CustomerProfilePayload,
)


class FakeMessage:
    def __init__(self, value: bytes = b"", error: Any = None) -> None:
        self._value = value
        self._error = error

    def value(self) -> bytes:
        return self._value

    def error(self) -> Any:
        return self._error


class FakeConsumer:
    def __init__(self, messages: list[Any]) -> None:
        self.messages = list(messages)
        self.subscriptions: list[list[str]] = []
        self.closed = False

    def subscribe(self, topics: list[str]) -> None:
        self.subscriptions.append(topics)

    def poll(self, timeout: float) -> Any:
        if self.messages:
            return self.messages.pop(0)
        raise StopIteration

    def close(self) -> None:
        self.closed = True


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


def test_consumer_deserializes_event(settings, event):
    fake = FakeConsumer(
        [FakeMessage(value=event.model_dump_json().encode())]
    )

    consumer = CustomerEventConsumer(settings=settings)
    consumer._consumer = fake

    result = next(consumer.consume())

    assert result == event


def test_consumer_close(settings):
    fake = FakeConsumer([])

    consumer = CustomerEventConsumer(settings=settings)
    consumer._consumer = fake

    consumer.close()

    assert fake.closed