from customer360.messaging.schemas import (
    CustomerEvent,
    CustomerEventType,
    CustomerProfilePayload,
)
from customer360.outbox.publisher import OutboxPublisher


class FakeRecord:
    def __init__(
        self,
        payload,
        event_id="11111111-1111-4111-8111-111111111111",
        retry_count=0,
        max_retries=5,
    ):
        self.payload = payload
        self.event_id = event_id
        self.retry_count = retry_count
        self.max_retries = max_retries
        self.dead_lettered = False
        self.status = "PENDING"


class FakeRepository:
    def __init__(self, records):
        self.records = records
        self.marked = []
        self.retried = []

    def pending(self):
        return self.records

    def mark_published(self, record):
        record.status = "PUBLISHED"
        self.marked.append(record)

    def increment_retry(self, record):
        record.retry_count += 1

        if record.retry_count >= record.max_retries:
            record.dead_lettered = True
            record.status = "FAILED"

        self.retried.append(record)


class FakeProducer:
    def __init__(self, should_fail=False):
        self.events = []
        self.flushed = False
        self.should_fail = should_fail

    def publish(self, event):
        if self.should_fail:
            raise RuntimeError("Kafka unavailable")

        self.events.append(event)

    def flush(self):
        self.flushed = True


def build_event():
    return CustomerEvent(
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


def test_publish_pending_marks_event_published():
    record = FakeRecord(build_event().model_dump_json())
    repository = FakeRepository([record])
    producer = FakeProducer()

    published = OutboxPublisher(repository, producer).publish_pending()

    assert published == 1
    assert len(producer.events) == 1
    assert repository.marked == [record]
    assert repository.retried == []
    assert producer.flushed is True


def test_publish_failure_increments_retry():
    record = FakeRecord(build_event().model_dump_json())
    repository = FakeRepository([record])
    producer = FakeProducer(should_fail=True)

    published = OutboxPublisher(repository, producer).publish_pending()

    assert published == 0
    assert record.retry_count == 1
    assert record.status == "PENDING"
    assert record.dead_lettered is False
    assert repository.retried == [record]
    assert repository.marked == []


def test_publish_failure_moves_event_to_dlq_after_max_retries():
    record = FakeRecord(
        build_event().model_dump_json(),
        retry_count=4,
        max_retries=5,
    )
    repository = FakeRepository([record])
    producer = FakeProducer(should_fail=True)

    published = OutboxPublisher(repository, producer).publish_pending()

    assert published == 0
    assert record.retry_count == 5
    assert record.status == "FAILED"
    assert record.dead_lettered is True