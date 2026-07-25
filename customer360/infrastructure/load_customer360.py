import logging

import pandas as pd

from customer360.config import PROCESSED_DATA_DIR
from customer360.infrastructure.database import (
    get_connection,
    initialize_database,
)
from customer360.logging_config import configure_logging


SOURCE_FILE = PROCESSED_DATA_DIR / "customer360_gold.csv"

configure_logging()
logger = logging.getLogger(__name__)


def load_customer360() -> None:
    if not SOURCE_FILE.exists():
        raise FileNotFoundError(
            f"Source file not found: {SOURCE_FILE}"
        )

    initialize_database()

    customer360 = pd.read_csv(SOURCE_FILE)

    connection = get_connection()

    try:
        customer360.to_sql(
            "customer360",
            connection,
            if_exists="replace",
            index=False,
        )

        row_count = connection.execute(
            "SELECT COUNT(*) FROM customer360"
        ).fetchone()[0]
    finally:
        connection.close()

    logger.info(
        "Loaded %s customer records into the database.",
        row_count,
    )


if __name__ == "__main__":
    load_customer360()
