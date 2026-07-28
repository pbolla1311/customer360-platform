"""Exercises the pure, DOM-free logic in the /workspace shell's
workspace-settings.js (role option list, invitation/API key status pill
classes).

workspace-settings.js exports its pure functions via `module.exports`
guarded by `typeof module !== "undefined"`, so this file can `require()` it
under Node without a DOM. Skipped if Node isn't available locally.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

SETTINGS_JS_PATH = (
    Path(__file__).resolve().parents[2]
    / "customer360"
    / "api"
    / "static"
    / "workspace"
    / "workspace-settings.js"
)

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")


def _run_node(expression: str):
    script = (
        f"const settings = require({json.dumps(str(SETTINGS_JS_PATH))}); "
        f"process.stdout.write(JSON.stringify({expression}));"
    )
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_role_options_covers_every_fixed_role():
    options = _run_node("settings.roleOptions()")
    values = [option["value"] for option in options]
    assert values == ["admin", "operations", "customer_success", "executive", "viewer"]
    assert all(option["label"] for option in options)


def test_role_options_returns_a_fresh_copy_each_call():
    first = _run_node("settings.roleOptions()")
    second = _run_node("settings.roleOptions()")
    assert first == second


def test_invitation_status_class_accepted():
    assert _run_node("settings.invitationStatusClass('accepted')") == "ws-status-pill--success"


def test_invitation_status_class_expired_and_revoked():
    assert _run_node("settings.invitationStatusClass('expired')") == "ws-status-pill--dlq"
    assert _run_node("settings.invitationStatusClass('revoked')") == "ws-status-pill--dlq"


def test_invitation_status_class_pending_defaults_to_failed_style():
    assert _run_node("settings.invitationStatusClass('pending')") == "ws-status-pill--failed"


def test_api_key_status_class_active_vs_revoked():
    assert _run_node("settings.apiKeyStatusClass('active')") == "ws-status-pill--success"
    assert _run_node("settings.apiKeyStatusClass('revoked')") == "ws-status-pill--dlq"
