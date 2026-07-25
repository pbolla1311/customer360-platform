from customer360.outbox.models import OutboxEvent


def test_outbox_model_defaults():
    event = OutboxEvent(
        event_id="123",
        event_type="UPSERTED",
        payload='{"id":"123"}',
        status="PENDING",
    )

    assert event.event_id == "123"
    assert event.event_type == "UPSERTED"
    assert event.payload == '{"id":"123"}'
    assert event.status == "PENDING"


def test_mark_published_fields():
    event = OutboxEvent(
        event_id="456",
        event_type="UPSERTED",
        payload='{"id":"456"}',
        status="PUBLISHED",
    )

    assert event.status == "PUBLISHED"