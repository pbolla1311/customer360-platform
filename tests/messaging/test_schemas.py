from datetime import UTC

import pytest
from pydantic import ValidationError

from customer360.messaging.schemas import (
    CustomerEvent,
    CustomerEventType,
    CustomerProfilePayload,
)


def valid_payload() -> dict:
    return {
        "customer_id": "1001",
        "first_name": "John",
        "last_name": "Smith",
        "email": "john.smith@example.com",
        "city": "Atlanta",
        "state": "GA",
        "transaction_count": 3,
        "total_spend": 240.0,
        "average_transaction_value": 80.0,
    }


def test_customer_profile_payload_accepts_valid_data() -> None:
    payload = CustomerProfilePayload(**valid_payload())

    assert payload.customer_id == "1001"
    assert payload.transaction_count == 3
    assert payload.total_spend == 240.0


def test_customer_profile_payload_rejects_negative_values() -> None:
    payload_data = valid_payload()
    payload_data["transaction_count"] = -1

    with pytest.raises(ValidationError):
        CustomerProfilePayload(**payload_data)


def test_customer_profile_payload_rejects_unknown_fields() -> None:
    payload_data = valid_payload()
    payload_data["unexpected_field"] = "invalid"

    with pytest.raises(ValidationError):
        CustomerProfilePayload(**payload_data)


def test_customer_event_generates_metadata() -> None:
    event = CustomerEvent(
        event_type=CustomerEventType.CREATED,
        payload=CustomerProfilePayload(**valid_payload()),
    )

    assert event.event_id is not None
    assert event.occurred_at.tzinfo == UTC
    assert event.source == "customer360-platform"


def test_customer_event_json_round_trip() -> None:
    original = CustomerEvent(
        event_type=CustomerEventType.UPDATED,
        payload=CustomerProfilePayload(**valid_payload()),
    )

    serialized = original.model_dump_json()
    restored = CustomerEvent.model_validate_json(serialized)

    assert restored == original
    assert restored.payload.customer_id == "1001"
    assert restored.event_type == CustomerEventType.UPDATED
def test_customer_event_supports_upserted_type() -> None:
    event = CustomerEvent(
        event_type=CustomerEventType.UPSERTED,
        payload=CustomerProfilePayload(**valid_payload()),
    )

    assert event.event_type == CustomerEventType.UPSERTED
    assert (
        event.model_dump(mode="json")["event_type"]
        == "customer.upserted"
    )
