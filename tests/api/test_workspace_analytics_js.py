"""Exercises the pure, DOM-free aggregation logic in the /workspace
Analytics view's workspace-analytics.js (revenue/growth/state/top-customer
computations over the real customer list).

See tests/api/test_demo_js.py for the require()-under-Node rationale this
harness follows exactly.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ANALYTICS_JS_PATH = (
    Path(__file__).resolve().parents[2]
    / "customer360"
    / "api"
    / "static"
    / "workspace"
    / "workspace-analytics.js"
)

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="Node.js is not installed"
)

CUSTOMERS = [
    {
        "customer_id": "CLOUD-0001",
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": "ada@example.com",
        "city": "London",
        "state": "LDN",
        "transaction_count": 4,
        "total_spend": 400.0,
        "average_transaction_value": 100.0,
        "created_at": "2026-01-05T00:00:00",
        "updated_at": "2026-01-05T00:00:00",
    },
    {
        "customer_id": "CLOUD-0002",
        "first_name": "Grace",
        "last_name": "Hopper",
        "email": "grace@example.com",
        "city": "Arlington",
        "state": "VA",
        "transaction_count": 1,
        "total_spend": 100.0,
        "average_transaction_value": 100.0,
        "created_at": "2026-01-06T00:00:00",
        "updated_at": "2026-01-06T00:00:00",
    },
    {
        "customer_id": "CLOUD-0003",
        "first_name": "Alan",
        "last_name": "Turing",
        "email": "alan@example.com",
        "city": "London",
        "state": "LDN",
        "transaction_count": 0,
        "total_spend": 0.0,
        "average_transaction_value": 0.0,
        "created_at": "2026-02-10T00:00:00",
        "updated_at": "2026-02-10T00:00:00",
    },
]


def _run_node(expression: str):
    script = (
        f"const an = require({json.dumps(str(ANALYTICS_JS_PATH))}); "
        f"process.stdout.write(JSON.stringify({expression}));"
    )
    result = subprocess.run(
        ["node", "-e", script],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_sum_total_spend_adds_every_customer():
    assert _run_node(f"an.sumTotalSpend({json.dumps(CUSTOMERS)})") == 500.0


def test_sum_transactions_adds_every_customer():
    assert _run_node(f"an.sumTransactions({json.dumps(CUSTOMERS)})") == 5


def test_average_order_value_divides_revenue_by_transactions():
    assert _run_node(f"an.averageOrderValue({json.dumps(CUSTOMERS)})") == 100.0


def test_average_order_value_zero_when_no_transactions():
    assert _run_node("an.averageOrderValue([])") == 0


def test_group_by_state_counts_and_sorts_descending():
    result = _run_node(f"an.groupByState({json.dumps(CUSTOMERS)})")
    assert result == {"categories": ["LDN", "VA"], "values": [2, 1]}


def test_group_by_state_uses_unknown_for_missing_state():
    customers = [dict(CUSTOMERS[0], state=None)]
    result = _run_node(f"an.groupByState({json.dumps(customers)})")
    assert result == {"categories": ["Unknown"], "values": [1]}


def test_iso_week_key_is_deterministic_and_matches_iso8601():
    # 2026-01-05 is a Monday in ISO week 2 of 2026.
    assert _run_node("an.isoWeekKey(new Date('2026-01-05T00:00:00Z'))") == "2026-W02"


def test_growth_by_week_buckets_and_sorts_chronologically():
    result = _run_node(f"an.growthByWeek({json.dumps(CUSTOMERS)})")
    assert result["categories"] == sorted(result["categories"])
    assert sum(result["values"]) == 3


def test_top_customers_sorts_by_spend_descending_and_respects_limit():
    result = _run_node(f"an.topCustomers({json.dumps(CUSTOMERS)}, 2)")
    assert [c["customer_id"] for c in result] == ["CLOUD-0001", "CLOUD-0002"]


def test_format_currency_matches_two_decimal_places():
    assert _run_node("an.formatCurrency(1234.5)") == "$1234.50"
    assert _run_node("an.formatCurrency(0)") == "$0.00"


# ---------------------------------------------------------------------
# v3.0 additions: CLV, active-customer count, pipeline success rate --
# all aware of the new customer.status ("active" | "archived") field
# ---------------------------------------------------------------------

CUSTOMERS_MIXED_STATUS = [
    dict(CUSTOMERS[0], status="active"),  # spend 400, 4 transactions
    dict(CUSTOMERS[1], status="archived"),  # spend 100, 1 transaction
    dict(CUSTOMERS[2], status="active", transaction_count=0),  # spend 0, 0 transactions
]


def test_non_archived_customers_excludes_archived_rows():
    result = _run_node(f"an.nonArchivedCustomers({json.dumps(CUSTOMERS_MIXED_STATUS)})")
    assert [c["customer_id"] for c in result] == ["CLOUD-0001", "CLOUD-0003"]


def test_non_archived_customers_treats_missing_status_as_active():
    # CUSTOMERS[0] has no "status" key at all -- simulates a row from
    # before the status column existed.
    assert "status" not in CUSTOMERS[0]
    result = _run_node(f"an.nonArchivedCustomers({json.dumps([CUSTOMERS[0]])})")
    assert len(result) == 1


def test_average_customer_lifetime_value_excludes_archived():
    result = _run_node(f"an.averageCustomerLifetimeValue({json.dumps(CUSTOMERS_MIXED_STATUS)})")
    # Only CLOUD-0001 (400.0) and CLOUD-0003 (0.0) are non-archived -> average 200.0
    assert result == 200.0


def test_average_customer_lifetime_value_zero_when_no_customers():
    assert _run_node("an.averageCustomerLifetimeValue([])") == 0


def test_count_active_customers_excludes_archived_and_zero_transaction_customers():
    result = _run_node(f"an.countActiveCustomers({json.dumps(CUSTOMERS_MIXED_STATUS)})")
    # CLOUD-0001 (active, 4 tx) counts; CLOUD-0002 (archived) and CLOUD-0003 (0 tx) don't.
    assert result == 1


def test_pipeline_success_rate_computes_percentage():
    kpis = {"messages_processed": 200, "successful_events": 150}
    assert _run_node(f"an.pipelineSuccessRate({json.dumps(kpis)})") == 75.0


def test_pipeline_success_rate_zero_when_no_messages_processed():
    kpis = {"messages_processed": 0, "successful_events": 0}
    assert _run_node(f"an.pipelineSuccessRate({json.dumps(kpis)})") == 0
