"""Exercises the pure, DOM-free logic in the /workspace Customers view's
workspace-customers.js (search filtering, edit-form diffing/validation).

See tests/api/test_demo_js.py for the require()-under-Node rationale this
harness follows exactly.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

CUSTOMERS_JS_PATH = (
    Path(__file__).resolve().parents[2]
    / "customer360"
    / "api"
    / "static"
    / "workspace"
    / "workspace-customers.js"
)

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="Node.js is not installed"
)

CUSTOMER = {
    "customer_id": "CLOUD-0001",
    "first_name": "Ada",
    "last_name": "Lovelace",
    "email": "ada@example.com",
    "city": "London",
    "state": "LDN",
    "transaction_count": 5,
    "total_spend": 250.5,
    "average_transaction_value": 50.1,
    "created_at": "2026-01-01T00:00:00",
    "updated_at": "2026-01-02T00:00:00",
}

HISTORY = [
    {
        "event": {
            "event_id": "EVT-000002",
            "event_type": "Email Changed",
            "customer_id": "CLOUD-0001",
            "created_at": "2026-01-03T00:00:00",
            "status": "success",
            "retry_count": 0,
            "failure_type": None,
        },
        "steps": [],
        "replay": False,
    },
    {
        "event": {
            "event_id": "EVT-000001",
            "event_type": "Customer Updated",
            "customer_id": "OTHER-0002",
            "created_at": "2026-01-02T00:00:00",
            "status": "success",
            "retry_count": 0,
            "failure_type": None,
        },
        "steps": [],
        "replay": False,
    },
]


def _run_node(expression: str):
    script = (
        f"const wc = require({json.dumps(str(CUSTOMERS_JS_PATH))}); "
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
    result = _run_node(f"wc.filterCustomers([{json.dumps(CUSTOMER)}], 'ada')")
    assert len(result) == 1


def test_filter_customers_no_match_returns_empty():
    result = _run_node(f"wc.filterCustomers([{json.dumps(CUSTOMER)}], 'zzz')")
    assert result == []


def test_derive_status_distinguishes_active_from_dormant():
    dormant = dict(CUSTOMER, transaction_count=0)
    assert _run_node(f"wc.deriveStatus({json.dumps(CUSTOMER)})") == "active"
    assert _run_node(f"wc.deriveStatus({json.dumps(dormant)})") == "dormant"


def test_diff_changed_fields_only_returns_actual_changes():
    edited = {
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": "ada.lovelace@example.com",
        "city": "Manchester",
        "state": "MCR",
    }
    result = _run_node(f"wc.diffChangedFields({json.dumps(CUSTOMER)}, {json.dumps(edited)})")

    assert result == {
        "email": "ada.lovelace@example.com",
        "city": "Manchester",
        "state": "MCR",
    }


def test_diff_changed_fields_empty_when_nothing_changed():
    same = {
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": "ada@example.com",
        "city": "London",
        "state": "LDN",
    }
    result = _run_node(f"wc.diffChangedFields({json.dumps(CUSTOMER)}, {json.dumps(same)})")
    assert result == {}


def test_validate_edit_form_rejects_blank_required_fields():
    fields = {
        "first_name": "",
        "last_name": "Lovelace",
        "email": "ada@example.com",
        "city": "London",
        "state": "LDN",
    }
    result = _run_node(f"wc.validateEditForm({json.dumps(fields)})")
    assert result["valid"] is False
    assert "first_name" in result["errors"]


def test_validate_edit_form_rejects_invalid_email():
    fields = {
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": "not-an-email",
        "city": "London",
        "state": "LDN",
    }
    result = _run_node(f"wc.validateEditForm({json.dumps(fields)})")
    assert result["valid"] is False
    assert "email" in result["errors"]


def test_validate_edit_form_accepts_well_formed_input():
    fields = {
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": "ada@example.com",
        "city": "London",
        "state": "LDN",
    }
    result = _run_node(f"wc.validateEditForm({json.dumps(fields)})")
    assert result == {"valid": True, "errors": {}}


def test_customer_history_filters_by_customer_id():
    result = _run_node(f"wc.customerHistory({json.dumps(HISTORY)}, 'CLOUD-0001')")
    assert len(result) == 1
    assert result[0]["event"]["event_id"] == "EVT-000002"


def test_customer_history_empty_when_no_match():
    result = _run_node(f"wc.customerHistory({json.dumps(HISTORY)}, 'NOPE')")
    assert result == []
