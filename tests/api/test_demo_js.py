"""Exercises the pure, DOM-free logic in the /demo dashboard's demo.js.

demo.js exports its search/lookup/derivation functions via `module.exports`
guarded by `typeof module !== "undefined"`, so this file can `require()` it
under Node without a DOM -- the same file is served to the browser unmodified.
Node ships on GitHub Actions' ubuntu-latest runners, so this needs no new
dependency; it's skipped if Node isn't available locally.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

DEMO_JS_PATH = (
    Path(__file__).resolve().parents[2]
    / "customer360"
    / "api"
    / "static"
    / "demo"
    / "demo.js"
)

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="Node.js is not installed"
)

CUSTOMERS = [
    {
        "customer_id": "DEMO-0001",
        "first_name": "Jordan",
        "last_name": "Reyes",
        "email": "jordan.reyes@example.com",
        "city": "Austin",
        "state": "TX",
        "transaction_count": 14,
        "total_spend": 1820.55,
        "average_transaction_value": 130.04,
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-02T00:00:00",
    },
    {
        "customer_id": "DEMO-0002",
        "first_name": "Priya",
        "last_name": "Nataraj",
        "email": "priya.nataraj@example.org",
        "city": "Seattle",
        "state": "WA",
        "transaction_count": 0,
        "total_spend": 0.0,
        "average_transaction_value": 0.0,
        "created_at": "2026-02-01T00:00:00",
        "updated_at": "2026-02-01T00:00:00",
    },
]


def _run_node(expression: str):
    script = (
        f"const demo = require({json.dumps(str(DEMO_JS_PATH))}); "
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


def test_filter_customers_matches_by_name():
    result = _run_node(f"demo.filterCustomers({json.dumps(CUSTOMERS)}, 'jordan')")

    assert [c["customer_id"] for c in result] == ["DEMO-0001"]


def test_filter_customers_matches_by_email_case_insensitive():
    result = _run_node(
        f"demo.filterCustomers({json.dumps(CUSTOMERS)}, 'PRIYA.NATARAJ')"
    )

    assert [c["customer_id"] for c in result] == ["DEMO-0002"]


def test_filter_customers_matches_by_customer_id():
    result = _run_node(f"demo.filterCustomers({json.dumps(CUSTOMERS)}, 'demo-0002')")

    assert [c["customer_id"] for c in result] == ["DEMO-0002"]


def test_filter_customers_empty_query_returns_all():
    result = _run_node(f"demo.filterCustomers({json.dumps(CUSTOMERS)}, '')")

    assert len(result) == len(CUSTOMERS)


def test_filter_customers_no_match_returns_empty_list():
    result = _run_node(f"demo.filterCustomers({json.dumps(CUSTOMERS)}, 'nonexistent')")

    assert result == []


def test_find_customer_by_id_selects_correct_customer():
    result = _run_node(f"demo.findCustomerById({json.dumps(CUSTOMERS)}, 'DEMO-0002')")

    assert result["customer_id"] == "DEMO-0002"


def test_find_customer_by_id_returns_null_when_missing():
    result = _run_node(f"demo.findCustomerById({json.dumps(CUSTOMERS)}, 'missing')")

    assert result is None


def test_derive_status_distinguishes_active_from_dormant():
    active = _run_node(f"demo.deriveStatus({json.dumps(CUSTOMERS[0])})")
    dormant = _run_node(f"demo.deriveStatus({json.dumps(CUSTOMERS[1])})")

    assert active == "active"
    assert dormant == "dormant"


def test_build_illustrative_timeline_is_deterministic_per_customer():
    first_run = _run_node(
        f"demo.buildIllustrativeTimeline({json.dumps(CUSTOMERS[0])})"
    )
    second_run = _run_node(
        f"demo.buildIllustrativeTimeline({json.dumps(CUSTOMERS[0])})"
    )

    assert first_run == second_run
    assert 2 <= len(first_run) <= 4


def test_build_illustrative_timeline_differs_across_customers():
    timeline_a = _run_node(
        f"demo.buildIllustrativeTimeline({json.dumps(CUSTOMERS[0])})"
    )
    timeline_b = _run_node(
        f"demo.buildIllustrativeTimeline({json.dumps(CUSTOMERS[1])})"
    )

    assert timeline_a != timeline_b


def test_compute_sample_events_processed_is_labeled_as_illustrative_by_formula():
    # Not a real events feed -- just confirms the deterministic formula the
    # frontend uses stays a pure function of the real fields it derives from.
    result = _run_node("demo.computeSampleEventsProcessed(10, 25)")

    assert result == 25 + 10 * 2
