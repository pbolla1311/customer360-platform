"""Exercises the pure, DOM-free logic in the /login page's login.js
(initials derivation, deterministic avatar color class).

login.js exports its pure functions via `module.exports` guarded by
`typeof module !== "undefined"`, so this file can `require()` it under Node
without a DOM. Skipped if Node isn't available locally.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

LOGIN_JS_PATH = (
    Path(__file__).resolve().parents[2] / "customer360" / "api" / "static" / "login" / "login.js"
)

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")


def _run_node(expression: str):
    script = (
        f"const login = require({json.dumps(str(LOGIN_JS_PATH))}); "
        f"process.stdout.write(JSON.stringify({expression}));"
    )
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_initials_for_two_word_name():
    assert _run_node("login.initialsFor('Sarah Johnson')") == "SJ"


def test_initials_for_single_word_name():
    assert _run_node("login.initialsFor('Cher')") == "CH"


def test_initials_for_empty_name_falls_back():
    assert _run_node("login.initialsFor('')") == "?"
    assert _run_node("login.initialsFor(null)") == "?"


def test_initials_for_collapses_extra_whitespace():
    assert _run_node("login.initialsFor('  Alex   Kim  ')") == "AK"


def test_avatar_class_for_is_deterministic():
    first = _run_node("login.avatarClassFor('sarah@acme.test')")
    second = _run_node("login.avatarClassFor('sarah@acme.test')")
    assert first == second
    assert first.startswith("login-user-avatar--")


def test_avatar_class_for_uses_fixed_palette():
    palette = {"blue", "cyan", "violet", "green", "amber"}
    for seed in ["a@example.com", "bb@example.com", "ccc@example.com", "dddd@example.com"]:
        cls = _run_node(f"login.avatarClassFor({json.dumps(seed)})")
        assert cls.replace("login-user-avatar--", "") in palette


def test_avatar_class_for_empty_seed_does_not_crash():
    cls = _run_node("login.avatarClassFor('')")
    assert cls.startswith("login-user-avatar--")
