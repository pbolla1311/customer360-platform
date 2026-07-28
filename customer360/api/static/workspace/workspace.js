(function () {
  "use strict";

  // ---------------------------------------------------------------------
  // Pure logic (no DOM access below this block) -- exercised directly
  // under Node in tests/api/test_workspace_js.py, and used unmodified by
  // the DOM wiring further down. Small, workspace-local reimplementations
  // of a couple of demo.js/pipeline.js helpers (formatCurrency,
  // formatThousands) are intentional: those files must stay byte-for-byte
  // unmodified (their own tests assert on them), and they don't expose
  // anything on `window` for a sibling script to reuse.
  // ---------------------------------------------------------------------

  var VIEWS = [
    "overview",
    "customers",
    "events",
    "pipeline",
    "monitoring",
    "analytics",
    "audit",
    "api-explorer",
    "settings",
  ];

  var VIEW_TITLES = {
    overview: "Overview",
    customers: "Customers",
    events: "Event Center",
    pipeline: "Pipeline",
    monitoring: "Monitoring",
    analytics: "Analytics",
    audit: "Audit Logs",
    "api-explorer": "API Explorer",
    settings: "Settings",
  };

  // v3.5 multi-tenancy: mirrors customer360/tenancy/permissions.py's
  // NAV_PERMISSIONS exactly -- the backend is the enforced source of
  // truth (403s on privileged actions regardless of what this hides),
  // this copy only drives which nav items the client shows.
  var NAV_PERMISSIONS = {
    overview: ["admin", "operations", "customer_success", "executive", "viewer"],
    customers: ["admin", "customer_success", "viewer"],
    events: ["admin", "operations", "customer_success", "viewer"],
    pipeline: ["admin", "operations", "viewer"],
    monitoring: ["admin", "operations", "viewer"],
    analytics: ["admin", "executive", "viewer"],
    audit: ["admin", "operations", "customer_success", "executive", "viewer"],
    "api-explorer": ["admin"],
    settings: ["admin"],
  };

  function canView(role, view) {
    var allowed = NAV_PERMISSIONS[view];
    if (!allowed) {
      return false;
    }
    return allowed.indexOf(role) !== -1;
  }

  var ROLE_LABELS = {
    admin: "Admin",
    operations: "Operations",
    customer_success: "Customer Success",
    executive: "Executive",
    viewer: "Viewer",
  };

  function roleLabel(role) {
    return ROLE_LABELS[role] || role || "";
  }

  // Deterministic "SJ"-from-"Sarah Johnson" initials, and a matching
  // deterministic avatar-color-class hash -- same techniques as login.js
  // (kept as an independent copy since each page's script is self-
  // contained, matching the app's existing per-page-file convention).
  function initialsFor(name) {
    var parts = String(name || "")
      .trim()
      .split(/\s+/)
      .filter(function (part) {
        return part.length > 0;
      });
    if (parts.length === 0) {
      return "?";
    }
    if (parts.length === 1) {
      return parts[0].slice(0, 2).toUpperCase();
    }
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }

  var AVATAR_PALETTE = ["blue", "cyan", "violet", "green", "amber"];

  function avatarClassFor(seed) {
    var text = String(seed || "");
    var hash = 0;
    for (var i = 0; i < text.length; i += 1) {
      hash = (hash * 31 + text.charCodeAt(i)) >>> 0;
    }
    return "login-user-avatar--" + AVATAR_PALETTE[hash % AVATAR_PALETTE.length];
  }

  function parseViewFromHash(hash) {
    var raw = String(hash || "").replace(/^#\/?/, "");
    var view = raw.split("/")[0];
    return VIEWS.indexOf(view) !== -1 ? view : "overview";
  }

  // The part after the view segment, e.g. "DEMO-0007" for
  // "#/customers/DEMO-0007" -- lets the Customers view deep-link to one
  // customer (from a direct URL or a Global Search result) without a
  // dedicated router.
  function parseHashParam(hash) {
    var raw = String(hash || "").replace(/^#\/?/, "");
    var parts = raw.split("/");
    return parts.length > 1 ? decodeURIComponent(parts[1]) : "";
  }

  function viewTitle(viewName) {
    return VIEW_TITLES[viewName] || "Workspace";
  }

  function formatThousands(value) {
    var sign = value < 0 ? "-" : "";
    var absValue = Math.round(Math.abs(value || 0));
    var digits = String(absValue);
    var grouped = "";

    for (var i = 0; i < digits.length; i += 1) {
      if (i > 0 && (digits.length - i) % 3 === 0) {
        grouped += ",";
      }
      grouped += digits[i];
    }

    return sign + grouped;
  }

  function formatCurrency(value) {
    var amount = typeof value === "number" && !isNaN(value) ? value : 0;
    var negative = amount < 0;
    var absAmount = Math.abs(amount);
    var whole = formatThousands(Math.floor(absAmount));
    var cents = Math.round((absAmount % 1) * 100);
    if (cents === 100) {
      // Rounding 0.995+ cents up can spill into the next whole unit.
      cents = 0;
      whole = formatThousands(Math.floor(absAmount) + 1);
    }
    var centsStr = cents < 10 ? "0" + cents : String(cents);
    return (negative ? "-$" : "$") + whole + "." + centsStr;
  }

  function deriveOverviewAlerts(services) {
    return (services || [])
      .filter(function (service) {
        return service.status === "warning" || service.status === "critical";
      })
      .map(function (service) {
        return {
          title: service.name + " is " + service.status,
          meta: "Latency " + service.latency_ms.toFixed(1) + " ms",
          severity: service.status,
        };
      });
  }

  // Real, derived operational signals -- never a fabricated generic to-do
  // list. Each task is only surfaced when the underlying count is
  // actually nonzero, and links straight to the view that explains it.
  function deriveUpcomingTasks(kpis, archivedCount) {
    var tasks = [];

    if (kpis && kpis.dlq_messages > 0) {
      tasks.push({
        title: kpis.dlq_messages + " event(s) in the Dead Letter Queue need review",
        meta: "Pipeline",
        href: "#/pipeline",
      });
    }

    if (kpis && kpis.retry_queue > 0) {
      tasks.push({
        title: kpis.retry_queue + " event(s) in the Retry Queue awaiting backoff",
        meta: "Pipeline",
        href: "#/pipeline",
      });
    }

    if (archivedCount > 0) {
      tasks.push({
        title: archivedCount + " customer(s) currently archived",
        meta: "Customers",
        href: "#/customers",
      });
    }

    return tasks;
  }

  // Single source of truth for "which event types count as a customer
  // edit" -- shared by Overview's "Recent Customer Updates" panel and
  // buildNotifications() below, instead of two copies of the same list.
  var CUSTOMER_UPDATE_EVENT_TYPES = [
    "Customer Updated",
    "Email Changed",
    "Address Changed",
    "Account Archived",
  ];

  // Derives the Notification Center's feed from data every other view
  // already fetches (pipeline history + service health) -- no new
  // backend endpoint, no fabricated events. "Successful recoveries" are
  // identified structurally: retry_count > 0 with a final status of
  // "success" can only mean the event failed at least once before this
  // engine's retry mechanism resolved it.
  function buildNotifications(history, services, invitations) {
    var notifications = [];

    (invitations || []).forEach(function (invitation) {
      if (invitation.status === "accepted" && invitation.accepted_at) {
        notifications.push({
          id: "invitation-" + invitation.id + "-accepted",
          title: invitation.email + " accepted their invitation",
          meta: roleLabel(invitation.role),
          timestamp: invitation.accepted_at,
          severity: "ok",
        });
      }
    });

    (history || []).forEach(function (entry) {
      var event = entry.event;
      if (event.status === "failed" || event.status === "dlq") {
        notifications.push({
          id: event.event_id + "-failure",
          title: event.event_type + " failed (" + event.customer_id + ")",
          meta: event.status.toUpperCase(),
          timestamp: event.created_at,
          severity: "critical",
        });
      } else if (event.retry_count > 0 && event.status === "success") {
        notifications.push({
          id: event.event_id + "-recovered",
          title: event.event_type + " recovered after " + event.retry_count + " retry attempt(s)",
          meta: event.customer_id,
          timestamp: event.created_at,
          severity: "ok",
        });
      } else if (CUSTOMER_UPDATE_EVENT_TYPES.indexOf(event.event_type) !== -1) {
        notifications.push({
          id: event.event_id + "-update",
          title: event.event_type + " (" + event.customer_id + ")",
          meta: "Customer update",
          timestamp: event.created_at,
          severity: "info",
        });
      }
    });

    (services || []).forEach(function (service) {
      if (service.status === "warning" || service.status === "critical") {
        notifications.push({
          id: "service-" + service.name,
          title: service.name + " is " + service.status,
          meta: "Latency " + service.latency_ms.toFixed(1) + " ms",
          timestamp: service.last_heartbeat,
          severity: service.status,
        });
      }
    });

    notifications.sort(function (a, b) {
      return new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime();
    });

    return notifications;
  }

  function countUnread(notifications, lastSeenIso) {
    if (!lastSeenIso) {
      return notifications.length;
    }
    var lastSeenMs = new Date(lastSeenIso).getTime();
    return notifications.filter(function (notification) {
      var ts = new Date(notification.timestamp).getTime();
      return !isNaN(ts) && ts > lastSeenMs;
    }).length;
  }

  function isNotificationUnread(notification, lastSeenIso) {
    if (!lastSeenIso) {
      return true;
    }
    var ts = new Date(notification.timestamp).getTime();
    var lastSeenMs = new Date(lastSeenIso).getTime();
    return !isNaN(ts) && ts > lastSeenMs;
  }

  var NOTIFICATION_ICONS = {
    critical: "⛔",
    warning: "⚠️",
    ok: "✓",
    info: "ℹ️",
  };

  function notificationIcon(severity) {
    return NOTIFICATION_ICONS[severity] || NOTIFICATION_ICONS.info;
  }

  // Splits a most-recent-first notification list into "today" (same
  // calendar day as `nowMs`) and "earlier" buckets for the Notification
  // Center's grouped display.
  function groupNotificationsByDay(notifications, nowMs) {
    var now = new Date(nowMs);
    var todayKey = now.getFullYear() + "-" + now.getMonth() + "-" + now.getDate();
    var groups = { today: [], earlier: [] };

    (notifications || []).forEach(function (notification) {
      var ts = new Date(notification.timestamp);
      var key = ts.getFullYear() + "-" + ts.getMonth() + "-" + ts.getDate();
      if (key === todayKey) {
        groups.today.push(notification);
      } else {
        groups.earlier.push(notification);
      }
    });

    return groups;
  }

  // Client-side aggregation over data other views already fetch -- no new
  // backend endpoint. Grouped by result type so the dropdown can label
  // each section (Customers / Events / Audit).
  function runGlobalSearch(query, data) {
    var needle = String(query || "")
      .toLowerCase()
      .trim();
    var result = { customers: [], events: [], audit: [] };

    if (!needle) {
      return result;
    }

    (data.customers || []).forEach(function (customer) {
      var haystack = (
        (customer.first_name || "") +
        " " +
        (customer.last_name || "") +
        " " +
        (customer.email || "") +
        " " +
        (customer.customer_id || "") +
        " " +
        (customer.tags || []).join(" ")
      ).toLowerCase();

      if (haystack.indexOf(needle) !== -1) {
        result.customers.push({
          label: (customer.first_name || "") + " " + (customer.last_name || "") + " (" + customer.customer_id + ")",
          meta: customer.email,
          href: "#/customers/" + encodeURIComponent(customer.customer_id),
        });
      }
    });

    (data.history || []).forEach(function (entry) {
      var event = entry.event;
      var haystack = (event.event_type + " " + event.customer_id + " " + event.event_id).toLowerCase();

      if (haystack.indexOf(needle) === -1) {
        return;
      }

      result.events.push({
        label: event.event_type + " — " + event.customer_id,
        meta: event.event_id,
        href: "#/events",
      });

      if (entry.audit) {
        result.audit.push({
          label: entry.audit.actor + " changed " + entry.audit.changes.join(", "),
          meta: event.event_id,
          href: "#/audit",
        });
      }
    });

    return result;
  }

  // Splits `text` into an ordered list of { text, matched } segments around
  // every case-insensitive occurrence of `query` -- returns structured data
  // rather than an HTML string so callers build `<mark>` nodes with
  // `textContent` (never `innerHTML`), avoiding any injection risk from
  // search-result text that ultimately comes from customer-entered data.
  function highlightMatch(text, query) {
    var source = String(text || "");
    var needle = String(query || "").trim();

    if (!needle) {
      return [{ text: source, matched: false }];
    }

    var lowerSource = source.toLowerCase();
    var lowerNeedle = needle.toLowerCase();
    var segments = [];
    var cursor = 0;

    while (cursor <= source.length) {
      var index = lowerSource.indexOf(lowerNeedle, cursor);
      if (index === -1) {
        segments.push({ text: source.slice(cursor), matched: false });
        break;
      }
      if (index > cursor) {
        segments.push({ text: source.slice(cursor, index), matched: false });
      }
      segments.push({ text: source.slice(index, index + needle.length), matched: true });
      cursor = index + needle.length;
    }

    return segments.filter(function (segment) {
      return segment.text.length > 0;
    });
  }

  var RECENT_SEARCHES_MAX = 5;

  // Pure list-management logic for the "recent searches" feature --
  // most-recent-first, deduplicated case-insensitively, capped at
  // RECENT_SEARCHES_MAX. Persistence (localStorage) is the DOM layer's job.
  function upsertRecentSearch(list, query) {
    var trimmed = String(query || "").trim();
    if (!trimmed) {
      return (list || []).slice(0, RECENT_SEARCHES_MAX);
    }
    var lower = trimmed.toLowerCase();
    var deduped = (list || []).filter(function (existing) {
      return String(existing || "").toLowerCase() !== lower;
    });
    deduped.unshift(trimmed);
    return deduped.slice(0, RECENT_SEARCHES_MAX);
  }

  var WorkspaceLogic = {
    VIEWS: VIEWS,
    parseViewFromHash: parseViewFromHash,
    parseHashParam: parseHashParam,
    viewTitle: viewTitle,
    formatThousands: formatThousands,
    formatCurrency: formatCurrency,
    deriveOverviewAlerts: deriveOverviewAlerts,
    deriveUpcomingTasks: deriveUpcomingTasks,
    CUSTOMER_UPDATE_EVENT_TYPES: CUSTOMER_UPDATE_EVENT_TYPES,
    buildNotifications: buildNotifications,
    countUnread: countUnread,
    isNotificationUnread: isNotificationUnread,
    notificationIcon: notificationIcon,
    groupNotificationsByDay: groupNotificationsByDay,
    runGlobalSearch: runGlobalSearch,
    highlightMatch: highlightMatch,
    upsertRecentSearch: upsertRecentSearch,
    canView: canView,
    roleLabel: roleLabel,
    initialsFor: initialsFor,
    avatarClassFor: avatarClassFor,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = WorkspaceLogic;
  }

  // ---------------------------------------------------------------------
  // Shared browser-only namespace: fetch/patch helpers and small DOM
  // utilities other workspace-*.js files attach their views to. Skipped
  // entirely outside a browser (e.g. under Node).
  // ---------------------------------------------------------------------

  if (typeof document === "undefined") {
    return;
  }

  var views = {};

  function fetchJson(url) {
    return fetch(url, { cache: "no-store" }).then(function (response) {
      if (!response.ok) {
        throw new Error("Request to " + url + " failed with " + response.status);
      }
      return response.json();
    });
  }

  function sendJson(method, url, body) {
    var options = { method: method, cache: "no-store" };
    if (body !== undefined) {
      options.headers = { "Content-Type": "application/json" };
      options.body = JSON.stringify(body);
    }

    return fetch(url, options).then(function (response) {
      return response
        .json()
        .catch(function () {
          return null;
        })
        .then(function (data) {
          if (!response.ok) {
            var message = (data && data.detail) || "Request to " + url + " failed with " + response.status;
            throw new Error(message);
          }
          return data;
        });
    });
  }

  function postJson(url, body) {
    return sendJson("POST", url, body);
  }

  function patchJson(url, body) {
    return sendJson("PATCH", url, body);
  }

  function animateValue(el, toValue, formatFn) {
    if (!el) {
      return;
    }
    var fromValue = parseFloat(el.getAttribute("data-value")) || 0;
    var duration = 500;
    var start = null;

    function step(timestamp) {
      if (start === null) {
        start = timestamp;
      }
      var progress = Math.min((timestamp - start) / duration, 1);
      var eased = 1 - Math.pow(1 - progress, 3);
      var current = fromValue + (toValue - fromValue) * eased;
      el.textContent = formatFn(current);

      if (progress < 1) {
        window.requestAnimationFrame(step);
      } else {
        el.textContent = formatFn(toValue);
        el.setAttribute("data-value", String(toValue));
      }
    }

    window.requestAnimationFrame(step);
  }

  function clearChildren(el) {
    if (el) {
      el.textContent = "";
    }
  }

  function relativeTimeLabel(isoTimestamp, nowMs) {
    var then = new Date(isoTimestamp).getTime();
    var diffSeconds = Math.max(0, Math.round((nowMs - then) / 1000));

    if (diffSeconds < 5) {
      return "just now";
    }
    if (diffSeconds < 60) {
      return diffSeconds + "s ago";
    }
    var minutes = Math.round(diffSeconds / 60);
    if (minutes < 60) {
      return minutes + "m ago";
    }
    var hours = Math.round(minutes / 60);
    return hours + "h ago";
  }

  window.WorkspaceLogic = WorkspaceLogic;
  window.Workspace = {
    fetchJson: fetchJson,
    postJson: postJson,
    patchJson: patchJson,
    animateValue: animateValue,
    clearChildren: clearChildren,
    relativeTimeLabel: relativeTimeLabel,
    registerView: function (name, handlers) {
      views[name] = handlers;
    },
    getHashParam: function () {
      return WorkspaceLogic.parseHashParam(window.location.hash);
    },
  };

  document.addEventListener("DOMContentLoaded", function () {
    var titleEl = document.getElementById("ws-view-title");
    var navLinks = Array.prototype.slice.call(document.querySelectorAll(".ws-nav-link"));
    var activeView = null;
    var currentRole = null;
    var currentOrganizationId = null;

    function setActiveNav(viewName) {
      navLinks.forEach(function (link) {
        link.classList.toggle("is-active", link.getAttribute("data-view") === viewName);
      });
    }

    function showView(viewName) {
      document.querySelectorAll(".ws-view").forEach(function (section) {
        section.classList.toggle("is-hidden", section.getAttribute("data-view") !== viewName);
      });
    }

    function activate(viewName) {
      if (activeView && views[activeView] && typeof views[activeView].deactivate === "function") {
        views[activeView].deactivate();
      }

      showView(viewName);
      setActiveNav(viewName);
      if (titleEl) {
        titleEl.textContent = WorkspaceLogic.viewTitle(viewName);
      }

      activeView = viewName;
      if (views[viewName] && typeof views[viewName].activate === "function") {
        views[viewName].activate();
      }
    }

    function onHashChange() {
      var view = WorkspaceLogic.parseViewFromHash(window.location.hash);
      if (currentRole && !WorkspaceLogic.canView(currentRole, view)) {
        view = "overview";
      }
      activate(view);
    }

    window.addEventListener("hashchange", onHashChange);

    function applyNavPermissions(role) {
      navLinks.forEach(function (link) {
        var view = link.getAttribute("data-view");
        link.classList.toggle("is-hidden", !WorkspaceLogic.canView(role, view));
      });
    }

    // -- Overview view --------------------------------------------------

    var ovEls = {
      kpiCustomers: document.getElementById("ov-kpi-customers"),
      kpiActive: document.getElementById("ov-kpi-active"),
      kpiRevenue: document.getElementById("ov-kpi-revenue"),
      kpiThroughput: document.getElementById("ov-kpi-throughput"),
      kpiFailed: document.getElementById("ov-kpi-failed"),
      kpiDlq: document.getElementById("ov-kpi-dlq"),
      kpiUsers: document.getElementById("ov-kpi-users"),
      kpiOrgs: document.getElementById("ov-kpi-orgs"),
      kpiInvites: document.getElementById("ov-kpi-invites"),
      stageMini: document.getElementById("ov-stage-mini"),
      alerts: document.getElementById("ov-alerts"),
      recentActivity: document.getElementById("ov-recent-activity"),
      recentCustomerUpdates: document.getElementById("ov-recent-customer-updates"),
      upcomingTasks: document.getElementById("ov-upcoming-tasks"),
      quickResetBtn: document.getElementById("ov-quick-reset"),
      quickResetStatus: document.getElementById("ov-quick-reset-status"),
    };

    var ovGrowthChart = null;

    function renderGrowthSparkline(customers) {
      var canvas = document.getElementById("ov-chart-growth");
      if (!canvas || typeof window.Chart === "undefined" || !window.AnalyticsLogic) {
        return;
      }
      var growth = window.AnalyticsLogic.growthByWeek(customers);
      var dataset = {
        label: "New customers",
        data: growth.values,
        borderColor: "#22d3ee",
        backgroundColor: "#22d3ee33",
        tension: 0.35,
        fill: true,
        pointRadius: 0,
        borderWidth: 2,
      };

      if (ovGrowthChart) {
        ovGrowthChart.data.labels = growth.categories;
        ovGrowthChart.data.datasets = [dataset];
        ovGrowthChart.update();
        return;
      }

      ovGrowthChart = new window.Chart(canvas, {
        type: "line",
        data: { labels: growth.categories, datasets: [dataset] },
        options: {
          animation: { duration: 400 },
          responsive: true,
          plugins: { legend: { display: false } },
          scales: {
            x: { ticks: { color: "#8b96a5", maxTicksLimit: 6 }, grid: { display: false } },
            y: { ticks: { color: "#8b96a5" }, grid: { color: "rgba(255,255,255,0.05)" }, beginAtZero: true },
          },
        },
      });
    }

    function renderUpcomingTasks(tasks) {
      if (!ovEls.upcomingTasks) {
        return;
      }
      clearChildren(ovEls.upcomingTasks);

      if (tasks.length === 0) {
        var empty = document.createElement("li");
        empty.className = "ws-empty-hint";
        empty.textContent = "No urgent tasks -- everything's healthy.";
        ovEls.upcomingTasks.appendChild(empty);
        return;
      }

      tasks.forEach(function (task) {
        var li = document.createElement("li");
        var link = document.createElement("a");
        link.href = task.href;
        link.className = "ws-item-title";
        link.textContent = task.title;
        var meta = document.createElement("span");
        meta.className = "ws-item-meta";
        meta.textContent = task.meta;
        li.appendChild(link);
        li.appendChild(meta);
        ovEls.upcomingTasks.appendChild(li);
      });
    }

    if (ovEls.quickResetBtn) {
      ovEls.quickResetBtn.addEventListener("click", function () {
        ovEls.quickResetBtn.disabled = true;
        postJson("/demo/api/pipeline/reset")
          .then(function () {
            if (ovEls.quickResetStatus) {
              ovEls.quickResetStatus.textContent = "Simulation data reset.";
              ovEls.quickResetStatus.className = "ws-edit-status ws-edit-status--ok";
            }
            loadOverview();
          })
          .catch(function (err) {
            if (ovEls.quickResetStatus) {
              ovEls.quickResetStatus.textContent = (err && err.message) || "Couldn't reset simulation data.";
              ovEls.quickResetStatus.className = "ws-edit-status ws-edit-status--error";
            }
          })
          .then(function () {
            ovEls.quickResetBtn.disabled = false;
          });
      });
    }

    function renderStageMini(stages) {
      clearChildren(ovEls.stageMini);
      stages.forEach(function (stage) {
        var chip = document.createElement("span");
        chip.className = "ws-stage-chip";
        chip.textContent = stage.name + ": " + formatValue(stage.count);
        ovEls.stageMini.appendChild(chip);
      });
    }

    function formatValue(value) {
      return WorkspaceLogic.formatThousands(value);
    }

    function renderAlertList(el, alerts, emptyText) {
      clearChildren(el);
      if (alerts.length === 0) {
        var empty = document.createElement("li");
        empty.className = "ws-empty-hint";
        empty.textContent = emptyText;
        el.appendChild(empty);
        return;
      }
      alerts.forEach(function (alert) {
        var li = document.createElement("li");
        li.className = "ws-alert--" + alert.severity;
        var title = document.createElement("span");
        title.className = "ws-item-title";
        title.textContent = alert.title;
        var meta = document.createElement("span");
        meta.className = "ws-item-meta";
        meta.textContent = alert.meta;
        li.appendChild(title);
        li.appendChild(meta);
        el.appendChild(li);
      });
    }

    function renderActivityList(el, entries, emptyText) {
      clearChildren(el);
      if (entries.length === 0) {
        var empty = document.createElement("li");
        empty.className = "ws-empty-hint";
        empty.textContent = emptyText;
        el.appendChild(empty);
        return;
      }
      var nowMs = Date.now();
      entries.forEach(function (entry) {
        var li = document.createElement("li");
        var title = document.createElement("span");
        title.className = "ws-item-title";
        title.textContent = entry.event.event_type + " — " + entry.event.customer_id;
        var meta = document.createElement("span");
        meta.className = "ws-item-meta";
        meta.textContent =
          entry.event.status.toUpperCase() + " · " + relativeTimeLabel(entry.event.created_at, nowMs);
        li.appendChild(title);
        li.appendChild(meta);
        el.appendChild(li);
      });
    }

    function loadOverview() {
      Promise.all([
        fetchJson("/demo/api/summary"),
        fetchJson("/demo/api/pipeline/summary"),
        fetchJson("/demo/api/pipeline/services"),
        fetchJson("/demo/api/pipeline/history?limit=20"),
        fetchJson("/demo/api/customers"),
      ])
        .then(function (results) {
          var summary = results[0];
          var pipeline = results[1];
          var services = results[2];
          var history = results[3];
          var customers = results[4];

          animateValue(ovEls.kpiCustomers, summary.total_customers, formatValue);
          animateValue(ovEls.kpiActive, summary.active_profiles, formatValue);

          var revenue = customers.reduce(function (sum, c) {
            return sum + (c.total_spend || 0);
          }, 0);
          animateValue(ovEls.kpiRevenue, revenue, WorkspaceLogic.formatCurrency);

          animateValue(ovEls.kpiThroughput, pipeline.kpis.events_per_sec, function (v) {
            return v.toFixed(2);
          });
          animateValue(ovEls.kpiFailed, pipeline.kpis.failed_events, formatValue);
          animateValue(ovEls.kpiDlq, pipeline.kpis.dlq_messages, formatValue);

          renderStageMini(pipeline.stages);
          renderAlertList(ovEls.alerts, WorkspaceLogic.deriveOverviewAlerts(services), "No active alerts.");
          renderActivityList(ovEls.recentActivity, history.slice(0, 8), "No recent activity yet.");

          var customerUpdates = history.filter(function (entry) {
            return WorkspaceLogic.CUSTOMER_UPDATE_EVENT_TYPES.indexOf(entry.event.event_type) !== -1;
          });
          renderActivityList(
            ovEls.recentCustomerUpdates,
            customerUpdates.slice(0, 8),
            "No customer edits yet -- edit a customer to see it here."
          );

          renderGrowthSparkline(customers);

          var archivedCount = customers.filter(function (c) {
            return (c.status || "active") === "archived";
          }).length;
          renderUpcomingTasks(WorkspaceLogic.deriveUpcomingTasks(pipeline.kpis, archivedCount));
        })
        .catch(function () {
          // Non-fatal: keep showing the last good snapshot.
        });

      if (currentOrganizationId) {
        Promise.all([
          fetchJson("/demo/api/organizations/" + currentOrganizationId + "/members"),
          fetchJson("/demo/api/organizations"),
          fetchJson("/demo/api/organizations/" + currentOrganizationId + "/invitations"),
        ])
          .then(function (results) {
            var members = results[0];
            var orgs = results[1];
            var invitations = results[2];

            var activeUserCount = members.filter(function (m) {
              return m.status === "active";
            }).length;
            animateValue(ovEls.kpiUsers, activeUserCount, formatValue);
            animateValue(ovEls.kpiOrgs, orgs.length, formatValue);

            var pendingCount = invitations.filter(function (i) {
              return i.status === "pending";
            }).length;
            animateValue(ovEls.kpiInvites, pendingCount, formatValue);
          })
          .catch(function () {
            // Non-admin roles can't list members/invitations -- KPIs just
            // keep showing their last value (0 on first load).
          });
      }
    }

    var overviewInterval = null;

    Workspace.registerView("overview", {
      activate: function () {
        loadOverview();
        overviewInterval = window.setInterval(loadOverview, 8000);
      },
      deactivate: function () {
        if (overviewInterval) {
          window.clearInterval(overviewInterval);
          overviewInterval = null;
        }
      },
    });

    // -- Global Search (topbar) ------------------------------------------

    var searchInput = document.getElementById("ws-global-search");
    var searchResultsEl = document.getElementById("ws-search-results");
    var searchCache = null; // { customers, history } -- fetched lazily, once
    var RECENT_SEARCHES_KEY = "ws-recent-searches";

    function readRecentSearches() {
      try {
        var raw = window.localStorage.getItem(RECENT_SEARCHES_KEY);
        var parsed = raw ? JSON.parse(raw) : [];
        return Array.isArray(parsed) ? parsed : [];
      } catch (err) {
        return [];
      }
    }

    function saveRecentSearch(query) {
      try {
        var updated = WorkspaceLogic.upsertRecentSearch(readRecentSearches(), query);
        window.localStorage.setItem(RECENT_SEARCHES_KEY, JSON.stringify(updated));
      } catch (err) {
        // localStorage unavailable (private browsing, quota) -- recent
        // searches just won't persist; search itself still works.
      }
    }

    function renderRecentSearches() {
      var recent = readRecentSearches();
      clearChildren(searchResultsEl);

      if (recent.length === 0) {
        searchResultsEl.classList.add("is-hidden");
        return;
      }

      var groupLabel = document.createElement("div");
      groupLabel.className = "ws-search-group-label";
      groupLabel.textContent = "Recent searches";
      searchResultsEl.appendChild(groupLabel);

      recent.forEach(function (query) {
        var item = document.createElement("button");
        item.type = "button";
        item.className = "ws-search-result ws-search-result--recent";
        item.textContent = query;
        item.addEventListener("click", function () {
          searchInput.value = query;
          runSearch();
        });
        searchResultsEl.appendChild(item);
      });

      searchResultsEl.classList.remove("is-hidden");
    }

    function loadSearchCache() {
      if (searchCache) {
        return Promise.resolve(searchCache);
      }
      return Promise.all([
        fetchJson("/demo/api/customers"),
        fetchJson("/demo/api/pipeline/history?limit=200"),
      ]).then(function (results) {
        searchCache = { customers: results[0], history: results[1] };
        return searchCache;
      });
    }

    function appendHighlighted(el, text, query) {
      WorkspaceLogic.highlightMatch(text, query).forEach(function (segment) {
        if (segment.matched) {
          var mark = document.createElement("mark");
          mark.className = "ws-search-highlight";
          mark.textContent = segment.text;
          el.appendChild(mark);
        } else {
          el.appendChild(document.createTextNode(segment.text));
        }
      });
    }

    function renderSearchGroup(container, label, items, query) {
      if (items.length === 0) {
        return;
      }
      var groupLabel = document.createElement("div");
      groupLabel.className = "ws-search-group-label";
      groupLabel.textContent = label;
      container.appendChild(groupLabel);

      items.slice(0, 5).forEach(function (item) {
        var link = document.createElement("a");
        link.className = "ws-search-result";
        link.href = item.href;
        appendHighlighted(link, item.label, query);
        if (item.meta) {
          link.appendChild(document.createTextNode(" — "));
          appendHighlighted(link, item.meta, query);
        }
        link.addEventListener("click", function () {
          hideSearchResults();
          saveRecentSearch(searchInput.value);
          searchInput.value = "";
        });
        container.appendChild(link);
      });
    }

    function hideSearchResults() {
      if (searchResultsEl) {
        searchResultsEl.classList.add("is-hidden");
      }
    }

    function runSearch() {
      var query = searchInput.value;
      if (!query.trim()) {
        renderRecentSearches();
        return;
      }

      loadSearchCache().then(function (cache) {
        var result = WorkspaceLogic.runGlobalSearch(query, cache);
        clearChildren(searchResultsEl);

        var total = result.customers.length + result.events.length + result.audit.length;
        if (total === 0) {
          if (window.UI) {
            searchResultsEl.appendChild(
              window.UI.emptyState({
                icon: "🔍",
                title: "No results found",
                description: 'Try a different name, email, customer ID, or event type for "' + query + '".',
              })
            );
          } else {
            var empty = document.createElement("div");
            empty.className = "ws-empty-hint";
            empty.textContent = "No matches.";
            searchResultsEl.appendChild(empty);
          }
        } else {
          renderSearchGroup(searchResultsEl, "Customers", result.customers, query);
          renderSearchGroup(searchResultsEl, "Events", result.events, query);
          renderSearchGroup(searchResultsEl, "Audit", result.audit, query);
          saveRecentSearch(query);
        }

        searchResultsEl.classList.remove("is-hidden");
      });
    }

    if (searchInput) {
      searchInput.addEventListener("input", runSearch);
      searchInput.addEventListener("focus", function () {
        if (!searchInput.value.trim()) {
          renderRecentSearches();
        }
      });
      searchInput.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
          hideSearchResults();
          searchInput.blur();
        }
      });
      document.addEventListener("click", function (event) {
        if (!searchInput.contains(event.target) && !searchResultsEl.contains(event.target)) {
          hideSearchResults();
        }
      });

      // "/" or Cmd/Ctrl+K focuses search from anywhere in the workspace,
      // as long as focus isn't already inside a text input/textarea/select
      // (so typing "/" in a customer-edit field doesn't hijack focus).
      document.addEventListener("keydown", function (event) {
        var isShortcut = event.key === "/" || ((event.metaKey || event.ctrlKey) && event.key === "k");
        if (!isShortcut) {
          return;
        }
        var active = document.activeElement;
        var isTyping =
          active &&
          (active.tagName === "INPUT" || active.tagName === "TEXTAREA" || active.tagName === "SELECT");
        if (isTyping && event.key === "/") {
          return;
        }
        event.preventDefault();
        searchInput.focus();
        searchInput.select();
      });
    }

    // -- Notification Center (topbar) ------------------------------------

    var notifBell = document.getElementById("ws-notif-bell");
    var notifBadge = document.getElementById("ws-notif-badge");
    var notifDropdown = document.getElementById("ws-notif-dropdown");
    var notifList = document.getElementById("ws-notif-list");
    var NOTIF_LAST_SEEN_KEY = "ws-notifications-last-seen";
    var latestNotifications = [];

    function readLastSeen() {
      try {
        return window.localStorage.getItem(NOTIF_LAST_SEEN_KEY);
      } catch (err) {
        return null;
      }
    }

    function writeLastSeen(iso) {
      try {
        window.localStorage.setItem(NOTIF_LAST_SEEN_KEY, iso);
      } catch (err) {
        // Private-browsing/storage-disabled: unread count just won't persist.
      }
    }

    function renderNotifBadge() {
      if (!notifBadge) {
        return;
      }
      var unread = WorkspaceLogic.countUnread(latestNotifications, readLastSeen());
      notifBadge.textContent = unread > 99 ? "99+" : String(unread);
      notifBadge.classList.toggle("is-hidden", unread === 0);
    }

    function renderNotifItem(notification, nowMs, lastSeenIso) {
      var li = document.createElement("li");
      li.className =
        "ws-notif-item ws-alert--" + (notification.severity === "ok" ? "healthy" : notification.severity);

      var icon = document.createElement("span");
      icon.className = "ws-notif-item-icon";
      icon.setAttribute("aria-hidden", "true");
      icon.textContent = WorkspaceLogic.notificationIcon(notification.severity);
      li.appendChild(icon);

      var body = document.createElement("span");
      body.className = "ws-notif-item-body";
      var title = document.createElement("span");
      title.className = "ws-item-title";
      title.textContent = notification.title;
      var meta = document.createElement("span");
      meta.className = "ws-item-meta";
      meta.textContent = notification.meta + " · " + relativeTimeLabel(notification.timestamp, nowMs);
      body.appendChild(title);
      body.appendChild(meta);
      li.appendChild(body);

      if (WorkspaceLogic.isNotificationUnread(notification, lastSeenIso)) {
        var dot = document.createElement("span");
        dot.className = "ws-notif-unread-dot";
        dot.setAttribute("aria-label", "Unread");
        li.appendChild(dot);
      }

      return li;
    }

    function renderNotifList() {
      if (!notifList) {
        return;
      }
      clearChildren(notifList);

      if (latestNotifications.length === 0) {
        if (window.UI) {
          var emptyWrap = document.createElement("li");
          emptyWrap.appendChild(
            window.UI.emptyState({
              icon: "🔔",
              title: "No notifications yet",
              description: "Failures, recoveries, customer edits, and accepted invitations will show up here.",
            })
          );
          notifList.appendChild(emptyWrap);
        } else {
          var empty = document.createElement("li");
          empty.className = "ws-empty-hint";
          empty.textContent = "No notifications yet.";
          notifList.appendChild(empty);
        }
        return;
      }

      var nowMs = Date.now();
      var lastSeenIso = readLastSeen();
      var grouped = WorkspaceLogic.groupNotificationsByDay(latestNotifications.slice(0, 20), nowMs);

      if (grouped.today.length > 0) {
        var todayLabel = document.createElement("li");
        todayLabel.className = "ws-search-group-label ws-notif-group-label";
        todayLabel.textContent = "Today";
        notifList.appendChild(todayLabel);
        grouped.today.forEach(function (notification) {
          notifList.appendChild(renderNotifItem(notification, nowMs, lastSeenIso));
        });
      }

      if (grouped.earlier.length > 0) {
        var earlierLabel = document.createElement("li");
        earlierLabel.className = "ws-search-group-label ws-notif-group-label";
        earlierLabel.textContent = "Earlier";
        notifList.appendChild(earlierLabel);
        grouped.earlier.forEach(function (notification) {
          notifList.appendChild(renderNotifItem(notification, nowMs, lastSeenIso));
        });
      }
    }

    function loadNotifications() {
      var invitationsPromise = currentOrganizationId
        ? fetchJson("/demo/api/organizations/" + currentOrganizationId + "/invitations").catch(function () {
            return [];
          })
        : Promise.resolve([]);

      Promise.all([
        fetchJson("/demo/api/pipeline/history?limit=100"),
        fetchJson("/demo/api/pipeline/services"),
        invitationsPromise,
      ])
        .then(function (results) {
          latestNotifications = WorkspaceLogic.buildNotifications(results[0], results[1], results[2]);
          renderNotifBadge();
          if (notifDropdown && !notifDropdown.classList.contains("is-hidden")) {
            renderNotifList();
          }
        })
        .catch(function () {});
    }

    if (notifBell) {
      notifBell.addEventListener("click", function () {
        var isOpen = !notifDropdown.classList.contains("is-hidden");
        if (isOpen) {
          notifDropdown.classList.add("is-hidden");
          notifBell.setAttribute("aria-expanded", "false");
          return;
        }
        renderNotifList();
        notifDropdown.classList.remove("is-hidden");
        notifBell.setAttribute("aria-expanded", "true");
        writeLastSeen(new Date().toISOString());
        renderNotifBadge();
      });

      document.addEventListener("click", function (event) {
        if (!notifBell.contains(event.target) && !notifDropdown.contains(event.target)) {
          notifDropdown.classList.add("is-hidden");
          notifBell.setAttribute("aria-expanded", "false");
        }
      });
    }

    loadNotifications();
    window.setInterval(loadNotifications, 10000);

    // -- Sidebar user + Sign Out (v3.5) -----------------------------------

    var sidebarAvatar = document.getElementById("ws-user-avatar");
    var sidebarUserName = document.getElementById("ws-user-name");
    var sidebarUserRole = document.getElementById("ws-user-role");
    var signoutBtn = document.getElementById("ws-signout-btn");

    function renderSidebarUser(session) {
      if (sidebarAvatar) {
        sidebarAvatar.className = "login-user-avatar " + WorkspaceLogic.avatarClassFor(session.user.email);
        sidebarAvatar.textContent = WorkspaceLogic.initialsFor(session.user.name);
      }
      if (sidebarUserName) {
        sidebarUserName.textContent = session.user.name;
      }
      if (sidebarUserRole) {
        sidebarUserRole.textContent = WorkspaceLogic.roleLabel(session.role);
      }
    }

    if (signoutBtn) {
      signoutBtn.addEventListener("click", function () {
        postJson("/demo/api/auth/logout").then(function () {
          window.location.href = "/login";
        });
      });
    }

    // -- Workspace switcher (v3.5) ----------------------------------------

    var switcherBtn = document.getElementById("ws-workspace-btn");
    var switcherNameEl = document.getElementById("ws-current-org-name");
    var switcherDropdown = document.getElementById("ws-workspace-dropdown");

    function closeSwitcher() {
      if (switcherDropdown) {
        switcherDropdown.classList.add("is-hidden");
      }
      if (switcherBtn) {
        switcherBtn.setAttribute("aria-expanded", "false");
      }
    }

    function setupWorkspaceSwitcher(session) {
      if (!switcherBtn || !switcherDropdown) {
        return;
      }
      switcherNameEl.textContent = session.organization.name;

      switcherBtn.addEventListener("click", function () {
        var isOpen = !switcherDropdown.classList.contains("is-hidden");
        if (isOpen) {
          closeSwitcher();
          return;
        }

        fetchJson("/demo/api/organizations").then(function (orgs) {
          clearChildren(switcherDropdown);
          orgs.forEach(function (org) {
            var option = document.createElement("button");
            option.type = "button";
            option.className =
              "ws-workspace-option" + (org.id === session.organization.id ? " is-current" : "");
            option.textContent = org.name;
            option.addEventListener("click", function () {
              closeSwitcher();
              if (org.id === session.organization.id) {
                return;
              }
              postJson("/demo/api/auth/switch-workspace", { organization_id: org.id }).then(
                function () {
                  window.location.reload();
                }
              );
            });
            switcherDropdown.appendChild(option);
          });
        });

        switcherDropdown.classList.remove("is-hidden");
        switcherBtn.setAttribute("aria-expanded", "true");
      });

      document.addEventListener("click", function (event) {
        if (!switcherBtn.contains(event.target) && !switcherDropdown.contains(event.target)) {
          closeSwitcher();
        }
      });
    }

    // -- Session gate + router kickoff ------------------------------------
    //
    // Every other view above has already registered its activate/
    // deactivate handlers by this point (harmless if never invoked) --
    // only the router itself waits on the session check, so an
    // unauthenticated visitor is redirected before any workspace data
    // loads rather than after a brief flash of it.

    fetchJson("/demo/api/auth/session")
      .then(function (session) {
        if (!session.user || !session.organization) {
          window.location.href = "/login";
          return;
        }

        currentRole = session.role;
        currentOrganizationId = session.organization.id;
        renderSidebarUser(session);
        setupWorkspaceSwitcher(session);
        applyNavPermissions(session.role);

        if (!window.location.hash) {
          window.location.hash = "#/overview";
        }
        onHashChange();
      })
      .catch(function () {
        window.location.href = "/login";
      });
  });
})();
