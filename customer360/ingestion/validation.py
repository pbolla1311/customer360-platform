import re

import pandas as pd


REQUIRED_COLUMNS = {
    "customer_id",
    "first_name",
    "last_name",
    "email",
    "city",
    "state",
    "signup_date",
}

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_required_columns(df: pd.DataFrame) -> None:
    missing_columns = REQUIRED_COLUMNS - set(df.columns)

    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Missing required columns: {missing}")


def validate_customer_ids(df: pd.DataFrame) -> None:
    if df["customer_id"].isna().any():
        raise ValueError("Customer records contain missing customer IDs.")

    if df["customer_id"].duplicated().any():
        duplicate_ids = (
            df.loc[df["customer_id"].duplicated(), "customer_id"]
            .astype(str)
            .tolist()
        )
        raise ValueError(f"Duplicate customer IDs found: {duplicate_ids}")


def validate_emails(df: pd.DataFrame) -> None:
    invalid_emails = df.loc[
        ~df["email"].astype(str).str.match(EMAIL_PATTERN),
        "email",
    ].tolist()

    if invalid_emails:
        raise ValueError(f"Invalid email addresses found: {invalid_emails}")


def validate_customers(df: pd.DataFrame) -> None:
    validate_required_columns(df)
    validate_customer_ids(df)
    validate_emails(df)
