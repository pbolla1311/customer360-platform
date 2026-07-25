from customer360.messaging.schemas import (
    CustomerEvent,
    CustomerEventType,
    CustomerProfilePayload,
)
from customer360.outbox.publisher import OutboxPublisher


class FakeRecord:
    def __init__(self, payload):
        self.payload = payload


class FakeRepository:
    def __init__(self, event):
        self._event = event
        self.marked = []

    def pending(self):
        return [FakeRecord(self._event.model_dump_json())]

    def mark_published(self, record):
        self.marked.append(record)


class FakeProducer:
    def __init__(self):
        self.events = []
        self.flushed = False

    def publish(self, event):
        self.events.append(event)

    def flush(self):
        self.flushed = True


def test_publish_pending():
    event = CustomerEvent(
        event_id="11111111-1111-4111-8111-111111111111",
        event_type=CustomerEventType.UPSERTED,
        occurred_at="2026-07-25T00:00:00Z",
        payload=CustomerProfilePayload(
            customer_id="1",
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            transaction_count=5,
            total_spend=250.0,
            average_transaction_value=50.0,
        ),
    )

    repository = FakeRepository(event)
    producer = FakeProducer()

    publisher = OutboxPublisher(repository, producer)

    published = publisher.publish_pending()

    assert published == 1
    assert len(producer.events) == 1
    assert producer.flushed is True
    assert len(repository.marked) == 1