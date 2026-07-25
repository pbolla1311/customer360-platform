from pathlib import Path

import pandas as pd

from database import get_connection, initialize_database


SOURCE_FILE = Path("datasets/processed/customer360_gold.csv")


def load_customer360() -> None:
    if not SOURCE_FILE.exists():
        raise FileNotFoundError(f"Source file not found: {SOURCE_FILE}")

    initialize_database()

    customer360 = pd.read_csv(SOURCE_FILE)

    connection = get_connection()

    customer360.to_sql(
        "customer360",
        connection,
        if_exists="replace",
        index=False,
    )

    row_count = connection.execute(
        "SELECT COUNT(*) FROM customer360"
    ).fetchone()[0]

    connection.close()

    print(f"Loaded {row_count} customer records into the database.")


if __name__ == "__main__":
    load_customer360()
