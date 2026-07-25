from pathlib import Path

import pandas as pd


RAW_FILE = Path("datasets/raw/transactions.csv")
PROCESSED_FILE = Path("datasets/processed/transactions_cleaned.csv")

REQUIRED_COLUMNS = {
    "transaction_id",
    "customer_id",
    "transaction_date",
    "amount",
    "category",
    "payment_method",
}


def load_transactions() -> pd.DataFrame:
    if not RAW_FILE.exists():
        raise FileNotFoundError(f"Input file not found: {RAW_FILE}")

    return pd.read_csv(RAW_FILE)


def validate_transactions(df: pd.DataFrame) -> None:
    missing_columns = REQUIRED_COLUMNS - set(df.columns)

    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Missing required columns: {missing}")

    if df["transaction_id"].isna().any():
        raise ValueError("Transaction records contain missing transaction IDs.")

    if df["transaction_id"].duplicated().any():
        raise ValueError("Duplicate transaction IDs found.")

    if df["customer_id"].isna().any():
        raise ValueError("Transaction records contain missing customer IDs.")

    numeric_amounts = pd.to_numeric(df["amount"], errors="coerce")

    if numeric_amounts.isna().any():
        raise ValueError("Transaction records contain invalid amounts.")

    if (numeric_amounts <= 0).any():
        raise ValueError("Transaction amounts must be greater than zero.")


def clean_transactions(df: pd.DataFrame) -> pd.DataFrame:
    cleaned_df = df.copy()

    cleaned_df.columns = [
        column.strip().lower()
        for column in cleaned_df.columns
    ]

    cleaned_df["transaction_id"] = pd.to_numeric(
        cleaned_df["transaction_id"],
        errors="coerce",
    )

    cleaned_df["customer_id"] = pd.to_numeric(
        cleaned_df["customer_id"],
        errors="coerce",
    )

    cleaned_df["transaction_date"] = pd.to_datetime(
        cleaned_df["transaction_date"],
        errors="coerce",
    )

    cleaned_df["amount"] = pd.to_numeric(
        cleaned_df["amount"],
        errors="coerce",
    ).round(2)

    cleaned_df["category"] = (
        cleaned_df["category"]
        .astype(str)
        .str.strip()
        .str.title()
    )

    cleaned_df["payment_method"] = (
        cleaned_df["payment_method"]
        .astype(str)
        .str.strip()
        .str.title()
    )

    cleaned_df = cleaned_df.drop_duplicates(
        subset=["transaction_id"],
    )

    cleaned_df = cleaned_df.dropna(
        subset=[
            "transaction_id",
            "customer_id",
            "transaction_date",
            "amount",
        ]
    )

    return cleaned_df


def save_transactions(df: pd.DataFrame) -> None:
    PROCESSED_FILE.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(PROCESSED_FILE, index=False)


def main() -> None:
    transactions = load_transactions()
    validate_transactions(transactions)

    cleaned_transactions = clean_transactions(transactions)
    save_transactions(cleaned_transactions)

    print(f"Processed {len(cleaned_transactions)} transaction records.")
    print(f"Output written to: {PROCESSED_FILE}")


if __name__ == "__main__":
    main()
