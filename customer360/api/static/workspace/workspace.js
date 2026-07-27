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
    return VIEWS.indexOf(raw) !== -1 ? raw : "overview";
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

  var WorkspaceLogic = {
    VIEWS: VIEWS,
    parseViewFromHash: parseViewFromHash,
    viewTitle: viewTitle,
    formatThousands: formatThousands,
    formatCurrency: formatCurrency,
    deriveOverviewAlerts: deriveOverviewAlerts,
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
    };

    var CUSTOMER_EVENT_TYPES = ["Customer Updated", "Email Changed", "Address Changed"];

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
            return CUSTOMER_EVENT_TYPES.indexOf(entry.event.event_type) !== -1;
          });
          renderActivityList(
            ovEls.recentCustomerUpdates,
            customerUpdates.slice(0, 8),
            "No customer edits yet -- edit a customer to see it here."
          );
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

    // -- Kick off the router ---------------------------------------------

    if (!window.location.hash) {
      window.location.hash = "#/overview";
    }
    onHashChange();
  });
})();
