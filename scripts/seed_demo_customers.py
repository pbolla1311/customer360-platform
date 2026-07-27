"""Seed fictional Customer360 demo records for the /demo dashboard.

Idempotent: running this repeatedly upserts the same set of customer_ids
rather than creating duplicates. Disabled by default -- it never runs on its
own, and refuses to run manually unless explicitly enabled, so a production
database can't be seeded by accident:

    ENABLE_DEMO_SEED=true python scripts/seed_demo_customers.py

or:

    python scripts/seed_demo_customers.py --force

All records use reserved example domains (example.com / example.org) and
fictional names -- no real personal information.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from customer360.infrastructure.models import Customer360Profile
from customer360.infrastructure.repository import Customer360Repository
from customer360.infrastructure.session import SessionLocal

DEMO_CUSTOMERS: list[dict[str, Any]] = [
    {
        "customer_id": "DEMO-0001",
        "first_name": "Jordan",
        "last_name": "Reyes",
        "email": "jordan.reyes@example.com",
        "city": "Austin",
        "state": "TX",
        "transaction_count": 14,
        "total_spend": 1820.55,
        "average_transaction_value": 130.04,
    },
    {
        "customer_id": "DEMO-0002",
        "first_name": "Priya",
        "last_name": "Nataraj",
        "email": "priya.nataraj@example.org",
        "city": "Seattle",
        "state": "WA",
        "transaction_count": 8,
        "total_spend": 642.10,
        "average_transaction_value": 80.26,
    },
    {
        "customer_id": "DEMO-0003",
        "first_name": "Marcus",
        "last_name": "Webb",
        "email": "marcus.webb@example.com",
        "city": "Denver",
        "state": "CO",
        "transaction_count": 0,
        "total_spend": 0.0,
        "average_transaction_value": 0.0,
    },
    {
        "customer_id": "DEMO-0004",
        "first_name": "Elena",
        "last_name": "Kowalski",
        "email": "elena.kowalski@example.org",
        "city": "Chicago",
        "state": "IL",
        "transaction_count": 23,
        "total_spend": 3110.75,
        "average_transaction_value": 135.25,
    },
    {
        "customer_id": "DEMO-0005",
        "first_name": "Samuel",
        "last_name": "Osei",
        "email": "samuel.osei@example.com",
        "city": "Atlanta",
        "state": "GA",
        "transaction_count": 5,
        "total_spend": 214.60,
        "average_transaction_value": 42.92,
    },
    {
        "customer_id": "DEMO-0006",
        "first_name": "Grace",
        "last_name": "Lindqvist",
        "email": "grace.lindqvist@example.org",
        "city": "Portland",
        "state": "OR",
        "transaction_count": 0,
        "total_spend": 0.0,
        "average_transaction_value": 0.0,
    },
    {
        "customer_id": "DEMO-0007",
        "first_name": "Hiro",
        "last_name": "Tanaka",
        "email": "hiro.tanaka@example.com",
        "city": "San Diego",
        "state": "CA",
        "transaction_count": 31,
        "total_spend": 4520.10,
        "average_transaction_value": 145.81,
    },
    {
        "customer_id": "DEMO-0008",
        "first_name": "Amara",
        "last_name": "Chukwu",
        "email": "amara.chukwu@example.org",
        "city": "Houston",
        "state": "TX",
        "transaction_count": 2,
        "total_spend": 58.40,
        "average_transaction_value": 29.20,
    },
    {
        "customer_id": "DEMO-0009",
        "first_name": "Liam",
        "last_name": "O'Connor",
        "email": "liam.oconnor@example.com",
        "city": "Boston",
        "state": "MA",
        "transaction_count": 17,
        "total_spend": 987.35,
        "average_transaction_value": 58.08,
    },
    {
        "customer_id": "DEMO-0010",
        "first_name": "Fatima",
        "last_name": "Haidari",
        "email": "fatima.haidari@example.org",
        "city": "Phoenix",
        "state": "AZ",
        "transaction_count": 9,
        "total_spend": 713.99,
        "average_transaction_value": 79.33,
    },
]


@dataclass(frozen=True)
class SeedResult:
    created: int
    updated: int


def seeding_enabled(*, force: bool = False) -> bool:
    """Whether the seed is allowed to run.

    Requires an explicit opt-in (env var or --force) so an operator can never
    trigger this against a database just by running the script by habit.
    """

    return force or os.getenv("ENABLE_DEMO_SEED", "").strip().lower() == "true"


def seed_demo_customers(
    session: Session,
    records: Sequence[dict[str, Any]] = DEMO_CUSTOMERS,
) -> SeedResult:
    """Upsert demo customer rows by customer_id. Safe to call repeatedly."""

    repository = Customer360Repository(session)
    created = 0
    updated = 0

    for record in records:
        existing = repository.get_by_customer_id(record["customer_id"])

        if existing is None:
            repository.create(Customer360Profile(**record))
            created += 1
        else:
            for field, value in record.items():
                if field != "customer_id":
                    setattr(existing, field, value)
            repository.update(existing)
            updated += 1

    return SeedResult(created=created, updated=updated)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Seed even if ENABLE_DEMO_SEED is not set to 'true'.",
    )
    args = parser.parse_args(argv)

    if not seeding_enabled(force=args.force):
        print(
            "Refusing to seed: set ENABLE_DEMO_SEED=true or pass --force.",
            file=sys.stderr,
        )
        return 1

    session = SessionLocal()
    try:
        result = seed_demo_customers(session)
    finally:
        session.close()

    print(
        f"Seeded demo customers: {result.created} created, "
        f"{result.updated} updated."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
