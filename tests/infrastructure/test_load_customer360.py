from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

from customer360.infrastructure.load_customer360 import (
    dataframe_to_profiles,
    profile_to_event,
    publish_customer_events,
)
from customer360.messaging.schemas import CustomerEventType


class FakeProducer:
    def __init__(self) -> None:
        self.events: List[Any] = []
        self.flush_calls = 0

    def publish(self, event: Any) -> None:
        self.events.append(event)

    def flush(self, timeout: float = 10.0) -> None:
        self.flush_calls += 1


def sample_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "customer_id": "C001",
                "first_name": "John",
                "last_name": "Smith",
                "email": "john@example.com",
                "city": "Atlanta",
                "state": "GA",
                "total_transactions": 3,
                "total_spend": 240.0,
                "average_transaction_value": 80.0,
            },
            {
                "customer_id": "C002",
                "first_name": "Jane",
                "last_name": "Doe",
                "email": "jane@example.com",
                "city": None,
                "state": None,
                "total_transactions": 2,
                "total_spend": 150.0,
                "average_transaction_value": 75.0,
            },
        ]
    )


def test_dataframe_to_profiles_maps_rows() -> None:
    profiles = dataframe_to_profiles(sample_dataframe())

    assert len(profiles) == 2
    assert profiles[0]["customer_id"] == "C001"
    assert profiles[0]["transaction_count"] == 3
    assert profiles[1]["city"] is None
    assert profiles[1]["state"] is None
    assert profiles[0]["created_at"] is not None
    assert profiles[0]["updated_at"] is not None


def test_profile_to_event_creates_upserted_event() -> None:
    profile: Dict[str, Any] = dataframe_to_profiles(
        sample_dataframe()
    )[0]

    event = profile_to_event(profile)

    assert event.event_type == CustomerEventType.UPSERTED
    assert event.source == "customer360-loader"
    assert event.payload.customer_id == "C001"
    assert event.payload.total_spend == 240.0


def test_publish_customer_events_publishes_every_profile() -> None:
    profiles = dataframe_to_profiles(sample_dataframe())
    producer = FakeProducer()

    published_count = publish_customer_events(
        profiles,
        producer,
    )

    assert published_count == 2
    assert len(producer.events) == 2
    assert producer.events[0].payload.customer_id == "C001"
    assert producer.events[1].payload.customer_id == "C002"
    assert producer.flush_calls == 1


def test_publish_customer_events_handles_empty_list() -> None:
    producer = FakeProducer()

    published_count = publish_customer_events([], producer)

    assert published_count == 0
    assert producer.events == []
    assert producer.flush_calls == 1