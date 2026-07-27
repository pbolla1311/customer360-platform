"""Exercises the pure, DOM-free logic in the /workspace Event Center /
Pipeline / Monitoring / Audit Logs views' workspace-pipeline.js.

See tests/api/test_demo_js.py for the require()-under-Node rationale this
harness follows exactly.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

PIPELINE_VIEW_JS_PATH = (
    Path(__file__).resolve().parents[2]
    / "customer360"
    / "api"
    / "static"
    / "workspace"
    / "workspace-pipeline.js"
)

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="Node.js is not installed"
)

STEPS = [
    {"stage": "Producer", "status": "ok", "processing_time_ms": 6.0},
    {"stage": "Kafka Topic", "status": "ok", "processing_time_ms": 14.0},
    {"stage": "Outbox", "status": "ok", "processing_time_ms": 5.0},
]

HISTORY = [
    {
        "event": {
            "event_id": "EVT-000002",
            "event_type": "Address Changed",
            "customer_id": "CLOUD-0001",
            "created_at": "2026-01-03T00:00:00",
            "status": "failed",
            "retry_count": 1,
            "failure_type": "consumer_failure",
        },
        "steps": STEPS,
        "replay": False,
    },
    {
        "event": {
            "event_id": "EVT-000001",
            "event_type": "Customer Updated",
            "customer_id": "CLOUD-0002",
            "created_at": "2026-01-02T00:00:00",
            "status": "success",
            "retry_count": 0,
            "failure_type": None,
        },
        "steps": STEPS,
        "replay": False,
    },
]


def _run_node(expression: str):
    script = (
        f"const wp = require({json.dumps(str(PIPELINE_VIEW_JS_PATH))}); "
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


def test_derive_stage_label_maps_each_status():
    assert _run_node("wp.deriveStageLabel('success')") == "Delivered"
    assert _run_node("wp.deriveStageLabel('failed')") == "Retry Queue"
    assert _run_node("wp.deriveStageLabel('dlq')") == "Dead Letter Queue"


def test_status_pill_class_maps_each_status():
    assert _run_node("wp.statusPillClass('success')") == "ws-status-pill--success"
    assert _run_node("wp.statusPillClass('failed')") == "ws-status-pill--failed"
    assert _run_node("wp.statusPillClass('dlq')") == "ws-status-pill--dlq"


def test_step_chip_class_maps_each_status():
    assert _run_node("wp.stepChipClass('ok')") == "ws-audit-step--ok"
    assert _run_node("wp.stepChipClass('failed')") == "ws-audit-step--failed"
    assert _run_node("wp.stepChipClass('pending')") == "ws-audit-step--pending"


def test_total_processing_ms_sums_all_steps():
    assert _run_node(f"wp.totalProcessingMs({json.dumps(STEPS)})") == 25.0


def test_total_processing_ms_zero_for_no_steps():
    assert _run_node("wp.totalProcessingMs([])") == 0


def test_filter_by_status_returns_only_matching_entries():
    result = _run_node(f"wp.filterByStatus({json.dumps(HISTORY)}, ['failed', 'dlq'])")
    assert [e["event"]["event_id"] for e in result] == ["EVT-000002"]


def test_filter_by_status_empty_when_no_match():
    result = _run_node(f"wp.filterByStatus({json.dumps(HISTORY)}, ['dlq'])")
    assert result == []


def test_format_thousands_groups_digits():
    assert _run_node("wp.formatThousands(1234567)") == "1,234,567"
    assert _run_node("wp.formatThousands(-500)") == "-500"
