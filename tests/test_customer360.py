import pandas as pd

from customer360.spark.customer360 import (
    build_customer360,
    build_transaction_metrics,
)


def test_build_transaction_metrics() -> None:
    transactions = pd.DataFrame(
        {
            "transaction_id": [1, 2, 3],
            "customer_id": [1001, 1001, 1002],
            "transaction_date": [
                "2024-01-01",
                "2024-01-05",
                "2024-01-10",
            ],
            "amount": [100.0, 50.0, 200.0],
        }
    )

    result = build_transaction_metrics(transactions)

    customer_1001 = result.loc[
        result["customer_id"] == 1001
    ].iloc[0]

    assert customer_1001["total_transactions"] == 2
    assert customer_1001["total_spend"] == 150.0
    assert customer_1001["average_transaction_value"] == 75.0


def test_build_customer360_includes_customer_without_transactions() -> None:
    customers = pd.DataFrame(
        {
            "customer_id": [1001, 1002],
            "first_name": ["John", "Emma"],
            "last_name": ["Smith", "Johnson"],
            "email": [
                "john@example.com",
                "emma@example.com",
            ],
            "city": ["Atlanta", "Dallas"],
            "state": ["GA", "TX"],
            "signup_date": [
                "2024-01-01",
                "2024-02-01",
            ],
        }
    )

    metrics = pd.DataFrame(
        {
            "customer_id": [1001],
            "total_transactions": [2],
            "total_spend": [350.0],
            "average_transaction_value": [175.0],
            "first_purchase_date": ["2024-03-01"],
            "last_purchase_date": ["2024-03-05"],
        }
    )

    result = build_customer360(customers, metrics)

    customer_1002 = result.loc[
        result["customer_id"] == 1002
    ].iloc[0]

    assert customer_1002["total_transactions"] == 0
    assert customer_1002["total_spend"] == 0
    assert customer_1002["average_transaction_value"] == 0
    assert customer_1002["customer_segment"] == "Standard"
