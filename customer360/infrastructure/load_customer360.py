import logging

import pandas as pd

from customer360.config import PROCESSED_DATA_DIR
from customer360.infrastructure.models import Customer360Profile
from customer360.infrastructure.repository import Customer360Repository
from customer360.infrastructure.session import SessionLocal
from customer360.logging_config import configure_logging

SOURCE_FILE = PROCESSED_DATA_DIR / "customer360_gold.csv"

configure_logging()
logger = logging.getLogger(__name__)


def load_customer360() -> None:
    if not SOURCE_FILE.exists():
        raise FileNotFoundError(f"Source file not found: {SOURCE_FILE}")

    dataframe = pd.read_csv(SOURCE_FILE)

    profiles = [
        Customer360Profile(
            customer_id=str(row.customer_id),
            first_name=str(row.first_name),
            last_name=str(row.last_name),
            email=str(row.email),
            city=None if pd.isna(row.city) else str(row.city),
            state=None if pd.isna(row.state) else str(row.state),
            transaction_count=int(row.total_transactions),
            total_spend=float(row.total_spend),
            average_transaction_value=float(
                row.average_transaction_value
            ),
        )
        for row in dataframe.itertuples(index=False)
    ]

    with SessionLocal() as session:
        repository = Customer360Repository(session)

        for profile in profiles:
            existing_profile = repository.get_by_customer_id(
                profile.customer_id
            )

            if existing_profile is None:
                repository.create(profile)
            else:
                existing_profile.first_name = profile.first_name
                existing_profile.last_name = profile.last_name
                existing_profile.email = profile.email
                existing_profile.city = profile.city
                existing_profile.state = profile.state
                existing_profile.transaction_count = (
                    profile.transaction_count
                )
                existing_profile.total_spend = profile.total_spend
                existing_profile.average_transaction_value = (
                    profile.average_transaction_value
                )

                repository.update(existing_profile)

    logger.info(
        "Loaded %s customer records into the database.",
        len(profiles),
    )


if __name__ == "__main__":
    load_customer360()