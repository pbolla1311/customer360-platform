"""Exercises the pure, DOM-free logic in the shared design system's
ui.js (toast icon selection).

ui.js exports its pure functions via `module.exports` guarded by
`typeof module !== "undefined"`, so this file can `require()` it under Node
without a DOM. Skipped if Node isn't available locally.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

UI_JS_PATH = (
    Path(__file__).resolve().parents[2] / "customer360" / "api" / "static" / "shared" / "ui.js"
)

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")


def _run_node(expression: str):
    script = (
        f"const ui = require({json.dumps(str(UI_JS_PATH))}); "
        f"process.stdout.write(JSON.stringify({expression}));"
    )
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_toast_icon_for_known_types():
    assert _run_node("ui.toastIconFor('success')") == "✓"
    assert _run_node("ui.toastIconFor('error')") == "✕"
    assert _run_node("ui.toastIconFor('info')") == "ℹ"


def test_toast_icon_for_unknown_type_falls_back_to_info():
    assert _run_node("ui.toastIconFor('made-up')") == "ℹ"
    assert _run_node("ui.toastIconFor(undefined)") == "ℹ"
