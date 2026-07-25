import logging
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Optional

import pandas as pd

from customer360.config import PROCESSED_DATA_DIR
from customer360.infrastructure.repository import Customer360Repository
from customer360.infrastructure.session import SessionLocal
from customer360.logging_config import configure_logging
from customer360.messaging.producer import CustomerEventProducer
from customer360.messaging.schemas import (
    CustomerEvent,
    CustomerEventType,
    CustomerProfilePayload,
)

SOURCE_FILE = PROCESSED_DATA_DIR / "customer360_gold.csv"
DEFAULT_BATCH_SIZE = 1000

configure_logging()
logger = logging.getLogger(__name__)


def dataframe_to_profiles(
    dataframe: pd.DataFrame,
) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    return [
        {
            "customer_id": str(row.customer_id),
            "first_name": str(row.first_name),
            "last_name": str(row.last_name),
            "email": str(row.email),
            "city": None if pd.isna(row.city) else str(row.city),
            "state": None if pd.isna(row.state) else str(row.state),
            "transaction_count": int(row.total_transactions),
            "total_spend": float(row.total_spend),
            "average_transaction_value": float(
                row.average_transaction_value
            ),
            "created_at": now,
            "updated_at": now,
        }
        for row in dataframe.itertuples(index=False)
    ]


def profile_to_event(
    profile: dict[str, Any],
) -> CustomerEvent:
    return CustomerEvent(
        event_type=CustomerEventType.UPSERTED,
        source="customer360-loader",
        payload=CustomerProfilePayload(
            customer_id=profile["customer_id"],
            first_name=profile["first_name"],
            last_name=profile["last_name"],
            email=profile["email"],
            city=profile["city"],
            state=profile["state"],
            transaction_count=profile["transaction_count"],
            total_spend=profile["total_spend"],
            average_transaction_value=profile[
                "average_transaction_value"
            ],
        ),
    )


def publish_customer_events(
    profiles: list[dict[str, Any]],
    producer: CustomerEventProducer,
) -> int:
    for profile in profiles:
        producer.publish(profile_to_event(profile))

    producer.flush()

    return len(profiles)


def load_customer360(
    batch_size: int = DEFAULT_BATCH_SIZE,
    producer: Optional[CustomerEventProducer] = None,
) -> int:
    if not SOURCE_FILE.exists():
        raise FileNotFoundError(
            f"Source file not found: {SOURCE_FILE}"
        )

    started_at = perf_counter()
    dataframe = pd.read_csv(SOURCE_FILE)
    profiles = dataframe_to_profiles(dataframe)

    with SessionLocal() as session:
        repository = Customer360Repository(session)
        processed_count = repository.bulk_upsert(
            profiles,
            batch_size=batch_size,
        )

    event_producer = producer or CustomerEventProducer()

    try:
        published_count = publish_customer_events(
            profiles,
            event_producer,
        )
    finally:
        if producer is None:
            event_producer.close()

    elapsed_seconds = perf_counter() - started_at

    logger.info(
        "Customer360 bulk load completed",
        extra={
            "processed_count": processed_count,
            "published_count": published_count,
            "batch_size": batch_size,
            "elapsed_seconds": round(elapsed_seconds, 3),
        },
    )

    return processed_count


if __name__ == "__main__":
    load_customer360()