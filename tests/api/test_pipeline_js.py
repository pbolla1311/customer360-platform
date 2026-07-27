"""Exercises the pure, DOM-free logic in /demo/pipeline's pipeline.js.

Same approach as tests/api/test_demo_js.py: pipeline.js exports its pure
functions via `module.exports` guarded by `typeof module !== "undefined"`,
so this file can `require()` it under Node without a DOM. Skipped if Node
isn't available.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

PIPELINE_JS_PATH = (
    Path(__file__).resolve().parents[2]
    / "customer360"
    / "api"
    / "static"
    / "demo"
    / "pipeline"
    / "pipeline.js"
)

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="Node.js is not installed"
)


def _run_node(expression: str):
    script = (
        f"const pipeline = require({json.dumps(str(PIPELINE_JS_PATH))}); "
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


def test_status_class_passes_through_known_statuses():
    assert _run_node("pipeline.statusClass('healthy')") == "healthy"
    assert _run_node("pipeline.statusClass('warning')") == "warning"
    assert _run_node("pipeline.statusClass('critical')") == "critical"


def test_status_class_defaults_unknown_values_to_healthy():
    assert _run_node("pipeline.statusClass('unknown')") == "healthy"


def test_pick_status_color_maps_each_status_to_a_distinct_color():
    healthy = _run_node("pipeline.pickStatusColor('healthy')")
    warning = _run_node("pipeline.pickStatusColor('warning')")
    critical = _run_node("pipeline.pickStatusColor('critical')")

    assert len({healthy, warning, critical}) == 3
    for color in (healthy, warning, critical):
        assert color.startswith("#")


def test_format_thousands_groups_large_numbers():
    assert _run_node("pipeline.formatThousands(1234567)") == "1,234,567"


def test_format_thousands_handles_small_numbers_without_separators():
    assert _run_node("pipeline.formatThousands(42)") == "42"


def test_format_thousands_rounds_and_handles_negative_values():
    assert _run_node("pipeline.formatThousands(-1500.6)") == "-1,501"


def test_relative_time_label_just_now_for_recent_timestamps():
    iso = "2027-01-15T00:00:00.000Z"
    label = _run_node(
        f"pipeline.relativeTimeLabel({json.dumps(iso)}, new Date({json.dumps(iso)}).getTime() + 2000)"
    )
    assert label == "just now"


def test_relative_time_label_seconds_minutes_hours():
    iso = "2027-01-15T00:00:00.000Z"

    ten_seconds = _run_node(
        f"pipeline.relativeTimeLabel({json.dumps(iso)}, new Date({json.dumps(iso)}).getTime() + 10000)"
    )
    five_minutes = _run_node(
        f"pipeline.relativeTimeLabel({json.dumps(iso)}, new Date({json.dumps(iso)}).getTime() + 300000)"
    )
    two_hours = _run_node(
        f"pipeline.relativeTimeLabel({json.dumps(iso)}, new Date({json.dumps(iso)}).getTime() + 7200000)"
    )

    assert ten_seconds == "10s ago"
    assert five_minutes == "5m ago"
    assert two_hours == "2h ago"


def test_build_event_list_model_maps_status_and_uppercases_label():
    entries = [
        {
            "timestamp": "2027-01-15T00:00:00Z",
            "event_type": "Retry Attempt",
            "status": "warning",
            "detail": "Retry Attempt — DEMO-0001",
        }
    ]

    result = _run_node(f"pipeline.buildEventListModel({json.dumps(entries)})")

    assert result[0]["statusClass"] == "warning"
    assert result[0]["statusLabel"] == "WARNING"
    assert result[0]["detail"] == "Retry Attempt — DEMO-0001"


def test_build_line_dataset_defaults_to_filled_area():
    dataset = _run_node(
        "pipeline.buildLineDataset('Messages / min', [1, 2, 3], '#3b82f6')"
    )

    assert dataset["label"] == "Messages / min"
    assert dataset["data"] == [1, 2, 3]
    assert dataset["borderColor"] == "#3b82f6"
    assert dataset["backgroundColor"] == "#3b82f633"
    assert dataset["fill"] is True


def test_build_line_dataset_can_disable_fill():
    dataset = _run_node(
        "pipeline.buildLineDataset('Latency', [1, 2], '#a78bfa', {fill: false})"
    )

    assert dataset["fill"] is False
