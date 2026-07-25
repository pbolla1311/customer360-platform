import pandas as pd

from customer360.config import RAW_DATA_DIR, PROCESSED_DATA_DIR
from customer360.ingestion.validation import validate_customers
from ingestion.validation import validate_customers
from config import RAW_DATA_DIR, PROCESSED_DATA_DIR

RAW_FILE = RAW_DATA_DIR / "customers.csv"
PROCESSED_FILE = PROCESSED_DATA_DIR / "customers_cleaned.csv"

def load_customers() -> pd.DataFrame:
    if not RAW_FILE.exists():
        raise FileNotFoundError(f"Input file not found: {RAW_FILE}")

    return pd.read_csv(RAW_FILE)


def clean_customers(df: pd.DataFrame) -> pd.DataFrame:
    cleaned_df = df.copy()

    cleaned_df.columns = [column.strip().lower() for column in cleaned_df.columns]

    cleaned_df["email"] = cleaned_df["email"].str.strip().str.lower()
    cleaned_df["first_name"] = cleaned_df["first_name"].str.strip().str.title()
    cleaned_df["last_name"] = cleaned_df["last_name"].str.strip().str.title()
    cleaned_df["city"] = cleaned_df["city"].str.strip().str.title()
    cleaned_df["state"] = cleaned_df["state"].str.strip().str.upper()
    cleaned_df["signup_date"] = pd.to_datetime(
        cleaned_df["signup_date"],
        errors="coerce",
    )

    cleaned_df = cleaned_df.drop_duplicates(subset=["customer_id"])
    cleaned_df = cleaned_df.dropna(
        subset=["customer_id", "email", "signup_date"]
    )

    return cleaned_df


def save_customers(df: pd.DataFrame) -> None:
    PROCESSED_FILE.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(PROCESSED_FILE, index=False)


def main() -> None:
    customers = load_customers()
    validate_customers(customers)

    cleaned_customers = clean_customers(customers)
    save_customers(cleaned_customers)

    print(f"Processed {len(cleaned_customers)} customer records.")
    print(f"Output written to: {PROCESSED_FILE}")


if __name__ == "__main__":
    main()
