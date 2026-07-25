import logging
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

import pandas as pd

from customer360.config import PROCESSED_DATA_DIR
from customer360.infrastructure.repository import Customer360Repository
from customer360.infrastructure.session import SessionLocal
from customer360.logging_config import configure_logging

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


def load_customer360(
    batch_size: int = DEFAULT_BATCH_SIZE,
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

    elapsed_seconds = perf_counter() - started_at

    logger.info(
        "Customer360 bulk load completed",
        extra={
            "processed_count": processed_count,
            "batch_size": batch_size,
            "elapsed_seconds": round(elapsed_seconds, 3),
        },
    )

    return processed_count


if __name__ == "__main__":
    load_customer360()