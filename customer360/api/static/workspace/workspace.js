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
  function buildNotifications(history, services) {
    var notifications = [];

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
    runGlobalSearch: runGlobalSearch,
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
      activate(WorkspaceLogic.parseViewFromHash(window.location.hash));
    }

    window.addEventListener("hashchange", onHashChange);

    // -- Overview view --------------------------------------------------

    var ovEls = {
      kpiCustomers: document.getElementById("ov-kpi-customers"),
      kpiActive: document.getElementById("ov-kpi-active"),
      kpiRevenue: document.getElementById("ov-kpi-revenue"),
      kpiThroughput: document.getElementById("ov-kpi-throughput"),
      kpiFailed: document.getElementById("ov-kpi-failed"),
      kpiDlq: document.getElementById("ov-kpi-dlq"),
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

    // -- Settings view ----------------------------------------------------

    var settingsResetBtn = document.getElementById("ws-settings-reset");
    var settingsResetStatus = document.getElementById("ws-settings-reset-status");
    var systemStatusEl = document.getElementById("ws-system-status");
    var settingsLoaded = false;

    if (settingsResetBtn) {
      settingsResetBtn.addEventListener("click", function () {
        settingsResetBtn.disabled = true;
        postJson("/demo/api/pipeline/reset")
          .then(function () {
            if (settingsResetStatus) {
              settingsResetStatus.textContent = "Simulation data reset.";
              settingsResetStatus.className = "ws-edit-status ws-edit-status--ok";
            }
          })
          .catch(function (err) {
            if (settingsResetStatus) {
              settingsResetStatus.textContent = (err && err.message) || "Couldn't reset simulation data.";
              settingsResetStatus.className = "ws-edit-status ws-edit-status--error";
            }
          })
          .then(function () {
            settingsResetBtn.disabled = false;
          });
      });
    }

    Workspace.registerView("settings", {
      activate: function () {
        if (settingsLoaded) {
          return;
        }
        settingsLoaded = true;
        fetchJson("/health")
          .then(function (health) {
            if (systemStatusEl) {
              systemStatusEl.textContent = health.status + " (v" + health.version + ")";
            }
          })
          .catch(function () {
            if (systemStatusEl) {
              systemStatusEl.textContent = "Unavailable";
            }
          });
      },
      deactivate: function () {},
    });

    // -- Global Search (topbar) ------------------------------------------

    var searchInput = document.getElementById("ws-global-search");
    var searchResultsEl = document.getElementById("ws-search-results");
    var searchCache = null; // { customers, history } -- fetched lazily, once

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

    function renderSearchGroup(container, label, items) {
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
        link.textContent = item.label + (item.meta ? " — " + item.meta : "");
        link.addEventListener("click", function () {
          hideSearchResults();
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
        hideSearchResults();
        return;
      }

      loadSearchCache().then(function (cache) {
        var result = WorkspaceLogic.runGlobalSearch(query, cache);
        clearChildren(searchResultsEl);

        var total = result.customers.length + result.events.length + result.audit.length;
        if (total === 0) {
          var empty = document.createElement("div");
          empty.className = "ws-empty-hint";
          empty.textContent = "No matches.";
          searchResultsEl.appendChild(empty);
        } else {
          renderSearchGroup(searchResultsEl, "Customers", result.customers);
          renderSearchGroup(searchResultsEl, "Events", result.events);
          renderSearchGroup(searchResultsEl, "Audit", result.audit);
        }

        searchResultsEl.classList.remove("is-hidden");
      });
    }

    if (searchInput) {
      searchInput.addEventListener("input", runSearch);
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

    function renderNotifList() {
      if (!notifList) {
        return;
      }
      clearChildren(notifList);

      if (latestNotifications.length === 0) {
        var empty = document.createElement("li");
        empty.className = "ws-empty-hint";
        empty.textContent = "No notifications yet.";
        notifList.appendChild(empty);
        return;
      }

      var nowMs = Date.now();
      latestNotifications.slice(0, 20).forEach(function (notification) {
        var li = document.createElement("li");
        li.className = "ws-alert--" + (notification.severity === "ok" ? "healthy" : notification.severity);
        var title = document.createElement("span");
        title.className = "ws-item-title";
        title.textContent = notification.title;
        var meta = document.createElement("span");
        meta.className = "ws-item-meta";
        meta.textContent = notification.meta + " · " + relativeTimeLabel(notification.timestamp, nowMs);
        li.appendChild(title);
        li.appendChild(meta);
        notifList.appendChild(li);
      });
    }

    function loadNotifications() {
      Promise.all([fetchJson("/demo/api/pipeline/history?limit=100"), fetchJson("/demo/api/pipeline/services")])
        .then(function (results) {
          latestNotifications = WorkspaceLogic.buildNotifications(results[0], results[1]);
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

    // -- Kick off the router ---------------------------------------------

    if (!window.location.hash) {
      window.location.hash = "#/overview";
    }
    onHashChange();
  });
})();
