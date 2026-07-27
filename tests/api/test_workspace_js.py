"""Exercises the pure, DOM-free logic in the /workspace shell's workspace.js
(hash routing, currency/thousands formatting, alert derivation).

workspace.js exports its pure functions via `module.exports` guarded by
`typeof module !== "undefined"`, so this file can `require()` it under Node
without a DOM -- the same file is served to the browser unmodified. Node
ships on GitHub Actions' ubuntu-latest runners, so this needs no new
dependency; it's skipped if Node isn't available locally.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

WORKSPACE_JS_PATH = (
    Path(__file__).resolve().parents[2]
    / "customer360"
    / "api"
    / "static"
    / "workspace"
    / "workspace.js"
)

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="Node.js is not installed"
)


def _run_node(expression: str):
    script = (
        f"const ws = require({json.dumps(str(WORKSPACE_JS_PATH))}); "
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


def test_parse_view_from_hash_recognizes_known_views():
    assert _run_node("ws.parseViewFromHash('#/customers')") == "customers"
    assert _run_node("ws.parseViewFromHash('#/api-explorer')") == "api-explorer"


def test_parse_view_from_hash_defaults_to_overview_for_unknown_or_empty():
    assert _run_node("ws.parseViewFromHash('#/nonsense')") == "overview"
    assert _run_node("ws.parseViewFromHash('')") == "overview"
    assert _run_node("ws.parseViewFromHash(undefined)") == "overview"


def test_view_title_maps_every_known_view():
    for view in [
        "overview",
        "customers",
        "events",
        "pipeline",
        "monitoring",
        "analytics",
        "audit",
        "api-explorer",
        "settings",
    ]:
        title = _run_node(f"ws.viewTitle({json.dumps(view)})")
        assert isinstance(title, str) and title


def test_format_thousands_groups_digits():
    assert _run_node("ws.formatThousands(1234567)") == "1,234,567"
    assert _run_node("ws.formatThousands(42)") == "42"
    assert _run_node("ws.formatThousands(-9500)") == "-9,500"


def test_format_currency_rounds_cents_correctly():
    assert _run_node("ws.formatCurrency(1234.5)") == "$1,234.50"
    assert _run_node("ws.formatCurrency(0)") == "$0.00"
    assert _run_node("ws.formatCurrency(999.995)") == "$1,000.00"
    assert _run_node("ws.formatCurrency(-42.999)") == "-$43.00"


def test_derive_overview_alerts_flags_only_unhealthy_services():
    services = [
        {"name": "API", "status": "healthy", "latency_ms": 12.0},
        {"name": "Consumer", "status": "critical", "latency_ms": 900.0},
        {"name": "Kafka", "status": "warning", "latency_ms": 55.5},
    ]
    alerts = _run_node(f"ws.deriveOverviewAlerts({json.dumps(services)})")

    assert [a["severity"] for a in alerts] == ["critical", "warning"]
    assert "Consumer" in alerts[0]["title"]


def test_derive_overview_alerts_empty_when_all_healthy():
    services = [{"name": "API", "status": "healthy", "latency_ms": 12.0}]
    assert _run_node(f"ws.deriveOverviewAlerts({json.dumps(services)})") == []
