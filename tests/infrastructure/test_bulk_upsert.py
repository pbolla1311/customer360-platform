from datetime import datetime

import pytest

from customer360.infrastructure.repository import Customer360Repository


def profile(customer_id: str) -> dict:
    now = datetime.utcnow()

    return {
        "customer_id": customer_id,
        "first_name": "John",
        "last_name": "Doe",
        "email": f"{customer_id}@example.com",
        "city": "Atlanta",
        "state": "GA",
        "transaction_count": 5,
        "total_spend": 250.0,
        "average_transaction_value": 50.0,
        "created_at": now,
        "updated_at": now,
    }


def test_bulk_insert(session):
    repo = Customer360Repository(session)

    rows = [
        profile("C001"),
        profile("C002"),
        profile("C003"),
    ]

    processed = repo.bulk_upsert(rows)

    assert processed == 3
    assert len(repo.list_all()) == 3


def test_bulk_update(session):
    repo = Customer360Repository(session)

    repo.bulk_upsert([profile("C001")])

    updated = profile("C001")
    updated["total_spend"] = 999.0
    updated["transaction_count"] = 20

    repo.bulk_upsert([updated])

    customer = repo.get_by_customer_id("C001")

    assert customer is not None
    assert customer.total_spend == 999.0
    assert customer.transaction_count == 20


def test_bulk_empty(session):
    repo = Customer360Repository(session)

    assert repo.bulk_upsert([]) == 0


def test_invalid_batch_size(session):
    repo = Customer360Repository(session)

    with pytest.raises(ValueError):
        repo.bulk_upsert(
            [profile("C001")],
            batch_size=0,
        )


def test_multiple_batches(session):
    repo = Customer360Repository(session)

    rows = [
        profile(f"C{i:03}")
        for i in range(25)
    ]

    processed = repo.bulk_upsert(
        rows,
        batch_size=10,
    )

    assert processed == 25
    assert len(repo.list_all()) == 25