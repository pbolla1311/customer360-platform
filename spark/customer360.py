from pathlib import Path

import pandas as pd


CUSTOMERS_FILE = Path("datasets/processed/customers_cleaned.csv")
TRANSACTIONS_FILE = Path(
    "datasets/processed/transactions_cleaned.csv"
)
OUTPUT_FILE = Path("datasets/processed/customer360_gold.csv")


def load_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    if not CUSTOMERS_FILE.exists():
        raise FileNotFoundError(
            f"Customer file not found: {CUSTOMERS_FILE}"
        )

    if not TRANSACTIONS_FILE.exists():
        raise FileNotFoundError(
            f"Transaction file not found: {TRANSACTIONS_FILE}"
        )

    customers = pd.read_csv(CUSTOMERS_FILE)
    transactions = pd.read_csv(TRANSACTIONS_FILE)

    return customers, transactions


def build_transaction_metrics(
    transactions: pd.DataFrame,
) -> pd.DataFrame:
    transactions["transaction_date"] = pd.to_datetime(
        transactions["transaction_date"],
        errors="coerce",
    )

    metrics = (
        transactions.groupby("customer_id")
        .agg(
            total_transactions=(
                "transaction_id",
                "count",
            ),
            total_spend=(
                "amount",
                "sum",
            ),
            average_transaction_value=(
                "amount",
                "mean",
            ),
            first_purchase_date=(
                "transaction_date",
                "min",
            ),
            last_purchase_date=(
                "transaction_date",
                "max",
            ),
        )
        .reset_index()
    )

    metrics["total_spend"] = metrics[
        "total_spend"
    ].round(2)

    metrics["average_transaction_value"] = metrics[
        "average_transaction_value"
    ].round(2)

    return metrics


def build_customer360(
    customers: pd.DataFrame,
    transaction_metrics: pd.DataFrame,
) -> pd.DataFrame:
    customer360 = customers.merge(
        transaction_metrics,
        on="customer_id",
        how="left",
    )

    customer360["total_transactions"] = (
        customer360["total_transactions"]
        .fillna(0)
        .astype(int)
    )

    customer360["total_spend"] = (
        customer360["total_spend"]
        .fillna(0)
        .round(2)
    )

    customer360["average_transaction_value"] = (
        customer360["average_transaction_value"]
        .fillna(0)
        .round(2)
    )

    customer360["customer_segment"] = pd.cut(
        customer360["total_spend"],
        bins=[-1, 100, 300, float("inf")],
        labels=[
            "Standard",
            "High Value",
            "Premium",
        ],
    )

    return customer360


def save_customer360(df: pd.DataFrame) -> None:
    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    df.to_csv(
        OUTPUT_FILE,
        index=False,
    )


def main() -> None:
    customers, transactions = load_data()

    transaction_metrics = build_transaction_metrics(
        transactions
    )

    customer360 = build_customer360(
        customers,
        transaction_metrics,
    )

    save_customer360(customer360)

    print(
        f"Created Customer 360 profiles for "
        f"{len(customer360)} customers."
    )

    print(f"Output written to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
