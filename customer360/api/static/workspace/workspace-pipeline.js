(function () {
  "use strict";

  // ---------------------------------------------------------------------
  // Pure logic (no DOM access below this block) -- exercised directly
  // under Node in tests/api/test_workspace_pipeline_js.py.
  // ---------------------------------------------------------------------

  function deriveStageLabel(status) {
    if (status === "dlq") {
      return "Dead Letter Queue";
    }
    if (status === "failed") {
      return "Retry Queue";
    }
    return "Delivered";
  }

  function statusPillClass(status) {
    if (status === "dlq") {
      return "ws-status-pill--dlq";
    }
    if (status === "failed") {
      return "ws-status-pill--failed";
    }
    return "ws-status-pill--success";
  }

  function stepChipClass(status) {
    if (status === "failed") {
      return "ws-audit-step--failed";
    }
    if (status === "pending") {
      return "ws-audit-step--pending";
    }
    return "ws-audit-step--ok";
  }

  function totalProcessingMs(steps) {
    return steps.reduce(function (sum, step) {
      return sum + (step.processing_time_ms || 0);
    }, 0);
  }

  function filterByStatus(history, statuses) {
    return history.filter(function (entry) {
      return statuses.indexOf(entry.event.status) !== -1;
    });
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

  var PipelineViewLogic = {
    deriveStageLabel: deriveStageLabel,
    statusPillClass: statusPillClass,
    stepChipClass: stepChipClass,
    totalProcessingMs: totalProcessingMs,
    filterByStatus: filterByStatus,
    formatThousands: formatThousands,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = PipelineViewLogic;
  }

  // ---------------------------------------------------------------------
  // DOM wiring -- skipped entirely outside a browser (e.g. under Node).
  // ---------------------------------------------------------------------

  if (typeof document === "undefined") {
    return;
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (!window.Workspace) {
      return;
    }

    var fetchJson = window.Workspace.fetchJson;
    var animateValue = window.Workspace.animateValue;
    var relativeTimeLabel = window.Workspace.relativeTimeLabel;

    // -- Event Center -----------------------------------------------------

    var eventTableBody = document.getElementById("ws-event-table-body");

    function renderEventTable(history) {
      if (!eventTableBody) {
        return;
      }
      eventTableBody.textContent = "";

      if (history.length === 0) {
        var row = document.createElement("tr");
        var cell = document.createElement("td");
        cell.colSpan = 7;
        cell.className = "ws-empty-hint";
        cell.textContent = "No events yet. Edit a customer or use Pipeline controls to generate one.";
        row.appendChild(cell);
        eventTableBody.appendChild(row);
        return;
      }

      var nowMs = Date.now();
      history.forEach(function (entry) {
        var event = entry.event;
        var tr = document.createElement("tr");

        [
          event.event_type,
          event.customer_id,
        ].forEach(function (text) {
          var td = document.createElement("td");
          td.textContent = text;
          tr.appendChild(td);
        });

        var statusTd = document.createElement("td");
        var pill = document.createElement("span");
        pill.className = "ws-status-pill " + PipelineViewLogic.statusPillClass(event.status);
        pill.textContent = event.status.toUpperCase();
        statusTd.appendChild(pill);
        tr.appendChild(statusTd);

        var stageTd = document.createElement("td");
        stageTd.textContent = PipelineViewLogic.deriveStageLabel(event.status);
        tr.appendChild(stageTd);

        var retryTd = document.createElement("td");
        retryTd.textContent = String(event.retry_count);
        tr.appendChild(retryTd);

        var processingTd = document.createElement("td");
        processingTd.textContent = PipelineViewLogic.totalProcessingMs(entry.steps).toFixed(1) + " ms";
        tr.appendChild(processingTd);

        var timeTd = document.createElement("td");
        timeTd.textContent = relativeTimeLabel(event.created_at, nowMs);
        tr.appendChild(timeTd);

        eventTableBody.appendChild(tr);
      });
    }

    var eventCenterInterval = null;

    function loadEventCenter() {
      fetchJson("/demo/api/pipeline/history?limit=100").then(renderEventTable).catch(function () {});
    }

    window.Workspace.registerView("events", {
      activate: function () {
        loadEventCenter();
        eventCenterInterval = window.setInterval(loadEventCenter, 6000);
      },
      deactivate: function () {
        if (eventCenterInterval) {
          window.clearInterval(eventCenterInterval);
          eventCenterInterval = null;
        }
      },
    });

    // -- Pipeline (embedded /demo/pipeline) --------------------------------

    var pipelineFrame = document.getElementById("ws-pipeline-frame");

    function applyPipelineEmbedTweaks() {
      try {
        var doc = pipelineFrame.contentDocument;
        if (!doc) {
          return;
        }
        var header = doc.querySelector(".pipeline-header");
        if (header) {
          header.classList.add("is-hidden");
        }
        var footer = doc.querySelector(".demo-footer");
        if (footer) {
          footer.classList.add("is-hidden");
        }
        // Real customer edits already produce events -- the embedded
        // Control Center keeps Inject Failure/Retry/Replay/Recover/Reset
        // (still useful operational tools) but not the manual "generate a
        // fake event" button, per the workspace's single-source-of-truth
        // story. Same-origin iframe, so this DOM reach-through is allowed;
        // wrapped in try/catch so a structural change to pipeline/index.html
        // degrades to "show the full page" instead of breaking anything.
        var generateButton = doc.getElementById("btn-generate");
        if (generateButton) {
          generateButton.classList.add("is-hidden");
        }
      } catch (err) {
        // Ignore -- embedded page still renders in full.
      }
    }

    if (pipelineFrame) {
      pipelineFrame.addEventListener("load", applyPipelineEmbedTweaks);
    }

    window.Workspace.registerView("pipeline", {
      activate: function () {},
      deactivate: function () {},
    });

    // -- Monitoring ---------------------------------------------------------

    var monEls = {
      messages: document.getElementById("mon-kpi-messages"),
      retry: document.getElementById("mon-kpi-retry"),
      dlq: document.getElementById("mon-kpi-dlq"),
      lag: document.getElementById("mon-kpi-lag"),
      latency: document.getElementById("mon-kpi-latency"),
      throughput: document.getElementById("mon-kpi-throughput"),
      servicesGrid: document.getElementById("mon-services-grid"),
      alerts: document.getElementById("mon-alerts"),
      recentFailures: document.getElementById("mon-recent-failures"),
    };

    function renderServicesGrid(services) {
      if (!monEls.servicesGrid) {
        return;
      }
      monEls.servicesGrid.textContent = "";
      var nowMs = Date.now();

      services.forEach(function (service) {
        var card = document.createElement("article");
        card.className = "service-card";

        var heading = document.createElement("div");
        heading.className = "service-card-heading";
        var name = document.createElement("span");
        name.className = "service-name";
        name.textContent = service.name;
        var dot = document.createElement("span");
        dot.className =
          "stage-dot stage-dot--" + (service.status === "healthy" ? "healthy" : service.status);
        heading.appendChild(name);
        heading.appendChild(dot);

        var latency = document.createElement("div");
        latency.className = "service-meta";
        var latencyLabel = document.createElement("span");
        latencyLabel.textContent = "Latency";
        var latencyValue = document.createElement("span");
        latencyValue.textContent = service.latency_ms.toFixed(1) + " ms";
        latency.appendChild(latencyLabel);
        latency.appendChild(latencyValue);

        var heartbeat = document.createElement("div");
        heartbeat.className = "service-meta";
        var heartbeatLabel = document.createElement("span");
        heartbeatLabel.textContent = "Heartbeat";
        var heartbeatValue = document.createElement("span");
        heartbeatValue.textContent = relativeTimeLabel(service.last_heartbeat, nowMs);
        heartbeat.appendChild(heartbeatLabel);
        heartbeat.appendChild(heartbeatValue);

        card.appendChild(heading);
        card.appendChild(latency);
        card.appendChild(heartbeat);
        monEls.servicesGrid.appendChild(card);
      });
    }

    function renderMonAlerts(services) {
      if (!monEls.alerts || !window.WorkspaceLogic) {
        return;
      }
      var alerts = window.WorkspaceLogic.deriveOverviewAlerts(services);
      monEls.alerts.textContent = "";

      if (alerts.length === 0) {
        var empty = document.createElement("li");
        empty.className = "ws-empty-hint";
        empty.textContent = "No active alerts.";
        monEls.alerts.appendChild(empty);
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
        monEls.alerts.appendChild(li);
      });
    }

    function renderRecentFailures(history) {
      if (!monEls.recentFailures) {
        return;
      }
      var failures = PipelineViewLogic.filterByStatus(history, ["failed", "dlq"]);
      monEls.recentFailures.textContent = "";

      if (failures.length === 0) {
        var empty = document.createElement("li");
        empty.className = "ws-empty-hint";
        empty.textContent = "No failures recorded.";
        monEls.recentFailures.appendChild(empty);
        return;
      }

      var nowMs = Date.now();
      failures.slice(0, 10).forEach(function (entry) {
        var li = document.createElement("li");
        var title = document.createElement("span");
        title.className = "ws-item-title";
        title.textContent = entry.event.event_type + " — " + entry.event.customer_id;
        var meta = document.createElement("span");
        meta.className = "ws-item-meta";
        meta.textContent =
          entry.event.status.toUpperCase() +
          " · retry #" +
          entry.event.retry_count +
          " · " +
          relativeTimeLabel(entry.event.created_at, nowMs);
        li.appendChild(title);
        li.appendChild(meta);
        monEls.recentFailures.appendChild(li);
      });
    }

    function formatKpi(value) {
      return PipelineViewLogic.formatThousands(value);
    }

    var monitoringInterval = null;

    function loadMonitoring() {
      Promise.all([
        fetchJson("/demo/api/pipeline/summary"),
        fetchJson("/demo/api/pipeline/services"),
        fetchJson("/demo/api/pipeline/history?limit=50"),
      ])
        .then(function (results) {
          var summary = results[0];
          var services = results[1];
          var history = results[2];

          animateValue(monEls.messages, summary.kpis.messages_processed, formatKpi);
          animateValue(monEls.retry, summary.kpis.retry_queue, formatKpi);
          animateValue(monEls.dlq, summary.kpis.dlq_messages, formatKpi);
          animateValue(monEls.lag, summary.kpis.consumer_lag, formatKpi);
          animateValue(monEls.latency, summary.kpis.avg_processing_time_ms, function (v) {
            return v.toFixed(1);
          });
          animateValue(monEls.throughput, summary.kpis.events_per_sec, function (v) {
            return v.toFixed(2);
          });

          renderServicesGrid(services);
          renderMonAlerts(services);
          renderRecentFailures(history);
        })
        .catch(function () {});
    }

    window.Workspace.registerView("monitoring", {
      activate: function () {
        loadMonitoring();
        monitoringInterval = window.setInterval(loadMonitoring, 6000);
      },
      deactivate: function () {
        if (monitoringInterval) {
          window.clearInterval(monitoringInterval);
          monitoringInterval = null;
        }
      },
    });

    // -- Audit Logs ---------------------------------------------------------

    var auditList = document.getElementById("ws-audit-list");

    function renderAuditTrail(history) {
      if (!auditList) {
        return;
      }
      auditList.textContent = "";

      if (history.length === 0) {
        var empty = document.createElement("li");
        empty.className = "ws-empty-hint";
        empty.textContent = "No audited events yet.";
        auditList.appendChild(empty);
        return;
      }

      var nowMs = Date.now();
      history.forEach(function (entry) {
        var li = document.createElement("li");

        var heading = document.createElement("div");
        heading.className = "ws-audit-entry-heading";
        var title = document.createElement("span");
        title.className = "ws-item-title";
        title.textContent = entry.event.event_type + " — " + entry.event.customer_id;
        var meta = document.createElement("span");
        meta.className = "ws-item-meta";
        meta.textContent = entry.event.event_id + " · " + relativeTimeLabel(entry.event.created_at, nowMs);
        heading.appendChild(title);
        heading.appendChild(meta);

        var steps = document.createElement("ol");
        steps.className = "ws-audit-steps";
        entry.steps.forEach(function (step) {
          var stepEl = document.createElement("li");
          stepEl.className = "ws-audit-step " + PipelineViewLogic.stepChipClass(step.status);
          stepEl.textContent = step.stage + " (" + step.status + ")";
          steps.appendChild(stepEl);
        });

        li.appendChild(heading);
        li.appendChild(steps);
        auditList.appendChild(li);
      });
    }

    var auditInterval = null;

    function loadAuditTrail() {
      fetchJson("/demo/api/pipeline/history?limit=100").then(renderAuditTrail).catch(function () {});
    }

    window.Workspace.registerView("audit", {
      activate: function () {
        loadAuditTrail();
        auditInterval = window.setInterval(loadAuditTrail, 8000);
      },
      deactivate: function () {
        if (auditInterval) {
          window.clearInterval(auditInterval);
          auditInterval = null;
        }
      },
    });

    // -- API Explorer (embedded /docs) ---------------------------------------

    window.Workspace.registerView("api-explorer", {
      activate: function () {},
      deactivate: function () {},
    });
  });
})();
