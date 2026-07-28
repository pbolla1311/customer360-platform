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
from datetime import datetime
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


# ---------------------------------------------------------------------
# v3.0 addition: Overview's real, derived "Upcoming Tasks" signals
# ---------------------------------------------------------------------


def test_derive_upcoming_tasks_empty_when_everything_is_healthy():
    kpis = {"dlq_messages": 0, "retry_queue": 0}
    assert _run_node(f"ws.deriveUpcomingTasks({json.dumps(kpis)}, 0)") == []


def test_derive_upcoming_tasks_flags_dlq_and_retry_queue():
    kpis = {"dlq_messages": 3, "retry_queue": 5}
    tasks = _run_node(f"ws.deriveUpcomingTasks({json.dumps(kpis)}, 0)")
    assert len(tasks) == 2
    assert all(task["href"] == "#/pipeline" for task in tasks)
    assert "3" in tasks[0]["title"]
    assert "5" in tasks[1]["title"]


def test_derive_upcoming_tasks_flags_archived_customers():
    kpis = {"dlq_messages": 0, "retry_queue": 0}
    tasks = _run_node(f"ws.deriveUpcomingTasks({json.dumps(kpis)}, 2)")
    assert len(tasks) == 1
    assert tasks[0]["href"] == "#/customers"
    assert "2" in tasks[0]["title"]


# ---------------------------------------------------------------------
# v3.0 additions: hash sub-paths (Customer Profile deep-linking),
# Notification Center, Global Search
# ---------------------------------------------------------------------


def test_parse_view_from_hash_ignores_sub_path():
    assert _run_node("ws.parseViewFromHash('#/customers/DEMO-0007')") == "customers"


def test_parse_hash_param_extracts_sub_path_segment():
    assert _run_node("ws.parseHashParam('#/customers/DEMO-0007')") == "DEMO-0007"


def test_parse_hash_param_empty_when_no_sub_path():
    assert _run_node("ws.parseHashParam('#/customers')") == ""
    assert _run_node("ws.parseHashParam('#/overview')") == ""


def test_parse_hash_param_decodes_uri_component():
    assert _run_node("ws.parseHashParam('#/customers/DEMO%200007')") == "DEMO 0007"


HISTORY_FOR_NOTIFICATIONS = [
    {
        "event": {
            "event_id": "EVT-000003",
            "event_type": "Address Changed",
            "customer_id": "CLOUD-0001",
            "created_at": "2026-01-05T00:00:00",
            "status": "failed",
            "retry_count": 1,
            "failure_type": "consumer_failure",
        },
        "steps": [],
        "replay": False,
    },
    {
        "event": {
            "event_id": "EVT-000002",
            "event_type": "Email Changed",
            "customer_id": "CLOUD-0002",
            "created_at": "2026-01-04T00:00:00",
            "status": "success",
            "retry_count": 2,
            "failure_type": None,
        },
        "steps": [],
        "replay": False,
    },
    {
        "event": {
            "event_id": "EVT-000001",
            "event_type": "Customer Updated",
            "customer_id": "CLOUD-0003",
            "created_at": "2026-01-03T00:00:00",
            "status": "success",
            "retry_count": 0,
            "failure_type": None,
        },
        "steps": [],
        "replay": False,
    },
]

SERVICES_FOR_NOTIFICATIONS = [
    {"name": "Consumer", "status": "critical", "latency_ms": 900.0, "last_heartbeat": "2026-01-05T00:00:00"},
    {"name": "API", "status": "healthy", "latency_ms": 12.0, "last_heartbeat": "2026-01-05T00:00:00"},
]


def test_build_notifications_flags_failures_recoveries_and_updates():
    notifications = _run_node(
        f"ws.buildNotifications({json.dumps(HISTORY_FOR_NOTIFICATIONS)}, {json.dumps(SERVICES_FOR_NOTIFICATIONS)})"
    )
    severities = [n["severity"] for n in notifications]
    assert "critical" in severities  # the failed event
    assert "ok" in severities  # retry_count > 0 and now success == recovered
    assert "info" in severities  # plain customer update
    # Service alert included too.
    assert any(n["id"] == "service-Consumer" for n in notifications)


def test_build_notifications_sorted_most_recent_first():
    notifications = _run_node(
        f"ws.buildNotifications({json.dumps(HISTORY_FOR_NOTIFICATIONS)}, [])"
    )
    timestamps = [n["timestamp"] for n in notifications]
    assert timestamps == sorted(timestamps, reverse=True)


def test_build_notifications_empty_for_empty_input():
    assert _run_node("ws.buildNotifications([], [])") == []


def test_count_unread_counts_everything_when_never_seen():
    notifications = [{"timestamp": "2026-01-05T00:00:00"}, {"timestamp": "2026-01-04T00:00:00"}]
    assert _run_node(f"ws.countUnread({json.dumps(notifications)}, null)") == 2


def test_count_unread_only_counts_after_last_seen():
    notifications = [{"timestamp": "2026-01-05T00:00:00"}, {"timestamp": "2026-01-01T00:00:00"}]
    result = _run_node(f"ws.countUnread({json.dumps(notifications)}, '2026-01-02T00:00:00')")
    assert result == 1


SEARCH_DATA = {
    "customers": [
        {
            "customer_id": "CLOUD-0001",
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada@example.com",
            "tags": ["vip"],
        },
    ],
    "history": [
        {
            "event": {
                "event_id": "EVT-000001",
                "event_type": "Email Changed",
                "customer_id": "CLOUD-0001",
                "created_at": "2026-01-01T00:00:00",
                "status": "success",
                "retry_count": 0,
                "failure_type": None,
            },
            "steps": [],
            "replay": False,
            "audit": {
                "actor": "Workspace User",
                "changes": ["email"],
                "before": {"email": "old@example.com"},
                "after": {"email": "ada@example.com"},
            },
        }
    ],
}


def test_run_global_search_matches_customer_by_name():
    result = _run_node(f"ws.runGlobalSearch('ada', {json.dumps(SEARCH_DATA)})")
    assert len(result["customers"]) == 1
    assert result["customers"][0]["href"] == "#/customers/CLOUD-0001"


def test_run_global_search_matches_customer_by_tag():
    result = _run_node(f"ws.runGlobalSearch('vip', {json.dumps(SEARCH_DATA)})")
    assert len(result["customers"]) == 1


def test_run_global_search_matches_events_and_audit():
    result = _run_node(f"ws.runGlobalSearch('Email Changed', {json.dumps(SEARCH_DATA)})")
    assert len(result["events"]) == 1
    assert len(result["audit"]) == 1


def test_run_global_search_empty_query_returns_empty_groups():
    result = _run_node(f"ws.runGlobalSearch('', {json.dumps(SEARCH_DATA)})")
    assert result == {"customers": [], "events": [], "audit": []}


def test_run_global_search_no_match_returns_empty_groups():
    result = _run_node(f"ws.runGlobalSearch('zzz-no-match', {json.dumps(SEARCH_DATA)})")
    assert result == {"customers": [], "events": [], "audit": []}


# ---------------------------------------------------------------------
# v3.5 additions: role-based nav gating, role labels, avatar identity
# ---------------------------------------------------------------------


def test_can_view_admin_sees_every_view():
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
        assert _run_node(f"ws.canView('admin', {json.dumps(view)})") is True


def test_can_view_viewer_cannot_manage_org_or_pipeline():
    assert _run_node("ws.canView('viewer', 'settings')") is False
    assert _run_node("ws.canView('viewer', 'api-explorer')") is False
    assert _run_node("ws.canView('viewer', 'overview')") is True


def test_can_view_operations_cannot_see_customers_or_analytics():
    assert _run_node("ws.canView('operations', 'customers')") is False
    assert _run_node("ws.canView('operations', 'analytics')") is False
    assert _run_node("ws.canView('operations', 'pipeline')") is True


def test_can_view_unknown_view_fails_closed():
    assert _run_node("ws.canView('admin', 'nonexistent-view')") is False


def test_role_label_maps_every_fixed_role():
    assert _run_node("ws.roleLabel('customer_success')") == "Customer Success"
    assert _run_node("ws.roleLabel('admin')") == "Admin"


def test_role_label_unknown_role_falls_back_to_raw_value():
    assert _run_node("ws.roleLabel('made-up-role')") == "made-up-role"


def test_initials_for_two_word_name():
    assert _run_node("ws.initialsFor('Mike Torres')") == "MT"


def test_initials_for_empty_name_falls_back():
    assert _run_node("ws.initialsFor('')") == "?"


def test_avatar_class_for_is_deterministic_and_in_palette():
    palette = {"blue", "cyan", "violet", "green", "amber"}
    first = _run_node("ws.avatarClassFor('priya@acme.test')")
    second = _run_node("ws.avatarClassFor('priya@acme.test')")
    assert first == second
    assert first.replace("login-user-avatar--", "") in palette


def test_build_notifications_includes_accepted_invitations():
    invitations = [
        {
            "id": 1,
            "email": "new.hire@acme.test",
            "role": "viewer",
            "status": "accepted",
            "accepted_at": "2026-01-06T00:00:00",
        },
        {
            "id": 2,
            "email": "still.pending@acme.test",
            "role": "operations",
            "status": "pending",
            "accepted_at": None,
        },
    ]
    notifications = _run_node(f"ws.buildNotifications([], [], {json.dumps(invitations)})")
    assert len(notifications) == 1
    assert notifications[0]["id"] == "invitation-1-accepted"
    assert "new.hire@acme.test" in notifications[0]["title"]
    assert notifications[0]["severity"] == "ok"


def test_build_notifications_without_invitations_arg_still_works():
    assert _run_node("ws.buildNotifications([], [])") == []


# ---------------------------------------------------------------------
# v4.0 additions: Global Search match highlighting + recent searches
# ---------------------------------------------------------------------


def test_highlight_match_splits_on_case_insensitive_match():
    segments = _run_node("ws.highlightMatch('Ada Lovelace', 'ada')")
    assert segments == [
        {"text": "Ada", "matched": True},
        {"text": " Lovelace", "matched": False},
    ]


def test_highlight_match_finds_multiple_occurrences():
    segments = _run_node("ws.highlightMatch('abcabc', 'a')")
    matched_segments = [s for s in segments if s["matched"]]
    assert len(matched_segments) == 2


def test_highlight_match_empty_query_returns_single_unmatched_segment():
    assert _run_node("ws.highlightMatch('hello', '')") == [{"text": "hello", "matched": False}]


def test_highlight_match_no_match_returns_single_unmatched_segment():
    assert _run_node("ws.highlightMatch('hello', 'zzz')") == [{"text": "hello", "matched": False}]


def test_upsert_recent_search_prepends_new_query():
    result = _run_node("ws.upsertRecentSearch(['b', 'a'], 'c')")
    assert result == ["c", "b", "a"]


def test_upsert_recent_search_deduplicates_case_insensitively():
    result = _run_node("ws.upsertRecentSearch(['Ada', 'b'], 'ada')")
    assert result == ["ada", "b"]


def test_upsert_recent_search_caps_at_five():
    result = _run_node("ws.upsertRecentSearch(['a', 'b', 'c', 'd', 'e'], 'f')")
    assert result == ["f", "a", "b", "c", "d"]


def test_upsert_recent_search_blank_query_leaves_list_unchanged():
    assert _run_node("ws.upsertRecentSearch(['a', 'b'], '  ')") == ["a", "b"]


# ---------------------------------------------------------------------
# v4.0 additions: Notification Center grouping, icons, unread state
# ---------------------------------------------------------------------


def test_notification_icon_maps_known_severities():
    assert _run_node("ws.notificationIcon('critical')") == "⛔"
    assert _run_node("ws.notificationIcon('warning')") == "⚠️"
    assert _run_node("ws.notificationIcon('ok')") == "✓"
    assert _run_node("ws.notificationIcon('info')") == "ℹ️"


def test_notification_icon_unknown_severity_falls_back_to_info():
    assert _run_node("ws.notificationIcon('made-up')") == "ℹ️"


def test_is_notification_unread_true_when_never_seen():
    notification = {"timestamp": "2026-01-05T00:00:00"}
    assert _run_node(f"ws.isNotificationUnread({json.dumps(notification)}, null)") is True


def test_is_notification_unread_false_when_before_last_seen():
    notification = {"timestamp": "2026-01-01T00:00:00"}
    result = _run_node(f"ws.isNotificationUnread({json.dumps(notification)}, '2026-01-02T00:00:00')")
    assert result is False


def test_is_notification_unread_true_when_after_last_seen():
    notification = {"timestamp": "2026-01-05T00:00:00"}
    result = _run_node(f"ws.isNotificationUnread({json.dumps(notification)}, '2026-01-02T00:00:00')")
    assert result is True


def test_group_notifications_by_day_splits_today_vs_earlier():
    now = datetime(2026, 1, 5, 12, 0, 0)
    notifications = [
        {"id": "today", "timestamp": "2026-01-05T08:00:00"},
        {"id": "yesterday", "timestamp": "2026-01-04T08:00:00"},
    ]
    result = _run_node(
        f"ws.groupNotificationsByDay({json.dumps(notifications)}, {int(now.timestamp() * 1000)})"
    )
    assert [n["id"] for n in result["today"]] == ["today"]
    assert [n["id"] for n in result["earlier"]] == ["yesterday"]


def test_group_notifications_by_day_empty_list():
    now_ms = int(datetime(2026, 1, 5).timestamp() * 1000)
    assert _run_node(f"ws.groupNotificationsByDay([], {now_ms})") == {"today": [], "earlier": []}
