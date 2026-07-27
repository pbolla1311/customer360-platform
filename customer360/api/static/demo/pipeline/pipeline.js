(function () {
  "use strict";

  // ---------------------------------------------------------------------
  // Pure logic (no DOM/Chart.js access below this block) -- exercised
  // directly under Node in tests/api/test_pipeline_js.py, and used
  // unmodified by the DOM wiring further down.
  // ---------------------------------------------------------------------

  var STATUS_COLORS = {
    healthy: "#34d399",
    warning: "#fbbf24",
    critical: "#f87171",
  };

  function statusClass(status) {
    if (status === "warning" || status === "critical") {
      return status;
    }
    return "healthy";
  }

  function pickStatusColor(status) {
    return STATUS_COLORS[statusClass(status)];
  }

  function formatThousands(value) {
    var sign = value < 0 ? "-" : "";
    var absValue = Math.round(Math.abs(value));
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

  function buildEventListModel(entries) {
    return entries.map(function (entry) {
      return {
        timestamp: entry.timestamp,
        detail: entry.detail,
        eventType: entry.event_type,
        statusClass: statusClass(entry.status),
        statusLabel: entry.status.toUpperCase(),
      };
    });
  }

  function buildLineDataset(label, data, color, options) {
    var opts = options || {};
    return {
      label: label,
      data: data,
      borderColor: color,
      backgroundColor: color + "33",
      tension: 0.35,
      fill: opts.fill !== false,
      pointRadius: 0,
      borderWidth: 2,
    };
  }

  var FAILURE_TYPE_LABELS = {
    consumer_failure: "Consumer Failure",
    kafka_timeout: "Kafka Timeout",
    database_timeout: "Database Timeout",
    serialization_error: "Serialization Error",
    validation_failure: "Validation Failure",
  };

  function describeFailureType(failureType) {
    return FAILURE_TYPE_LABELS[failureType] || failureType;
  }

  function computeButtonStates(state) {
    var hasCurrentFailed = !!(state.current_event && state.current_event.status === "failed");
    return {
      replayDisabled: !state.has_replayable_event,
      retryDisabled: !hasCurrentFailed,
    };
  }

  function buildControlStatusMessage(action, trace) {
    var event = trace.event;

    if (action === "generate") {
      return (
        'Generated "' + event.event_type + '" for ' + event.customer_id + " -- delivered successfully."
      );
    }
    if (action === "replay") {
      return "Replayed the last event (" + event.event_id + ") -- pure visualization, no new writes.";
    }
    if (action === "failure") {
      return (
        "Injected " +
        describeFailureType(event.failure_type) +
        " on " +
        event.event_id +
        " -- now in the Retry Queue."
      );
    }
    if (action === "retry") {
      if (event.status === "success") {
        return "Retry #" + event.retry_count + " succeeded -- " + event.event_id + " reached PostgreSQL.";
      }
      if (event.status === "dlq") {
        return (
          "Retry #" +
          event.retry_count +
          " exhausted the retry limit -- " +
          event.event_id +
          " moved to the Dead Letter Queue."
        );
      }
      return (
        "Retry #" +
        event.retry_count +
        " failed again -- " +
        describeFailureType(event.failure_type) +
        " is still active. Try Recover Consumer, then retry again."
      );
    }
    return "";
  }

  function stageAnimationSchedule(steps, stepDurationMs) {
    var duration = stepDurationMs || 450;
    var cursor = 0;
    return steps.map(function (step) {
      var entry = { stage: step.stage, status: step.status, startMs: cursor, endMs: cursor + duration };
      cursor += duration;
      return entry;
    });
  }

  var PipelineLogic = {
    statusClass: statusClass,
    pickStatusColor: pickStatusColor,
    formatThousands: formatThousands,
    relativeTimeLabel: relativeTimeLabel,
    buildEventListModel: buildEventListModel,
    buildLineDataset: buildLineDataset,
    describeFailureType: describeFailureType,
    computeButtonStates: computeButtonStates,
    buildControlStatusMessage: buildControlStatusMessage,
    stageAnimationSchedule: stageAnimationSchedule,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = PipelineLogic;
  }

  // ---------------------------------------------------------------------
  // DOM wiring -- skipped entirely outside a browser (e.g. under Node).
  // ---------------------------------------------------------------------

  if (typeof document === "undefined") {
    return;
  }

  document.addEventListener("DOMContentLoaded", function () {
    var KPI_FIELDS = [
      { id: "kpi-messages-processed", key: "messages_processed", decimals: 0 },
      { id: "kpi-successful-events", key: "successful_events", decimals: 0 },
      { id: "kpi-failed-events", key: "failed_events", decimals: 0 },
      { id: "kpi-retry-queue", key: "retry_queue", decimals: 0 },
      { id: "kpi-dlq-messages", key: "dlq_messages", decimals: 0 },
      { id: "kpi-avg-processing-time", key: "avg_processing_time_ms", decimals: 1 },
      { id: "kpi-events-per-sec", key: "events_per_sec", decimals: 2 },
      { id: "kpi-consumer-lag", key: "consumer_lag", decimals: 0 },
    ];

    var STAGE_ORDER = [
      "Producer",
      "Kafka Topic",
      "Outbox",
      "Consumer",
      "Retry Queue",
      "Dead Letter Queue",
      "PostgreSQL",
    ];

    var flowTrack = document.getElementById("pipeline-flow-track");
    var eventList = document.getElementById("event-stream-list");
    var servicesGrid = document.getElementById("services-grid");
    var flowSelect = document.getElementById("flow-customer-select");
    var flowHint = document.getElementById("flow-hint");
    var flowTimeline = document.getElementById("flow-timeline");

    var btnGenerate = document.getElementById("btn-generate");
    var btnReplay = document.getElementById("btn-replay");
    var failureTypeSelect = document.getElementById("failure-type-select");
    var btnInjectFailure = document.getElementById("btn-inject-failure");
    var btnRetry = document.getElementById("btn-retry");
    var btnRecover = document.getElementById("btn-recover");
    var btnReset = document.getElementById("btn-reset");
    var controlStatus = document.getElementById("control-status");

    if (!flowTrack || !eventList || !servicesGrid) {
      return;
    }

    var charts = {};

    function fetchJson(url) {
      return fetch(url, { cache: "no-store" }).then(function (response) {
        if (!response.ok) {
          throw new Error("Request to " + url + " failed with " + response.status);
        }
        return response.json();
      });
    }

    function postJson(url, body) {
      var options = { method: "POST", cache: "no-store" };
      if (body) {
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
              var message =
                (data && data.detail) || "Request to " + url + " failed with " + response.status;
              throw new Error(message);
            }
            return data;
          });
      });
    }

    function formatKpi(rawValue, decimals) {
      if (decimals === 0) {
        return PipelineLogic.formatThousands(rawValue);
      }
      return rawValue.toFixed(decimals);
    }

    function animateKpiValue(el, toValue, decimals) {
      var fromValue = parseFloat(el.getAttribute("data-value")) || 0;
      var duration = 600;
      var start = null;

      function step(timestamp) {
        if (start === null) {
          start = timestamp;
        }
        var progress = Math.min((timestamp - start) / duration, 1);
        var eased = 1 - Math.pow(1 - progress, 3);
        var current = fromValue + (toValue - fromValue) * eased;
        el.textContent = formatKpi(current, decimals);

        if (progress < 1) {
          window.requestAnimationFrame(step);
        } else {
          el.textContent = formatKpi(toValue, decimals);
          el.setAttribute("data-value", String(toValue));
        }
      }

      window.requestAnimationFrame(step);
    }

    function renderKpis(kpis) {
      KPI_FIELDS.forEach(function (field) {
        var el = document.getElementById(field.id);
        if (el) {
          animateKpiValue(el, kpis[field.key], field.decimals);
        }
      });
    }

    function stageSlug(name) {
      return name.toLowerCase().replace(/\s+/g, "-");
    }

    function buildStageNodes() {
      STAGE_ORDER.forEach(function (name, index) {
        var node = document.createElement("div");
        node.className = "stage-node";
        node.id = "stage-" + stageSlug(name);

        var label = document.createElement("span");
        label.className = "stage-name";
        label.textContent = name;

        var count = document.createElement("span");
        count.className = "stage-count";
        count.textContent = "0";

        var dot = document.createElement("span");
        dot.className = "stage-dot stage-dot--healthy";

        node.appendChild(label);
        node.appendChild(count);
        node.appendChild(dot);
        flowTrack.appendChild(node);

        if (index < STAGE_ORDER.length - 1) {
          var connector = document.createElement("div");
          connector.className = "stage-connector";
          flowTrack.appendChild(connector);
        }
      });
    }

    // Updates existing stage nodes in place rather than destroying and
    // rebuilding them on every poll -- animateTrace() below highlights
    // these same node elements by id while an action's animation plays, so
    // they need to survive a passive summary refresh landing mid-animation.
    function renderStages(stages) {
      if (flowTrack.children.length === 0) {
        buildStageNodes();
      }

      stages.forEach(function (stage) {
        var node = document.getElementById("stage-" + stageSlug(stage.name));
        if (!node) {
          return;
        }
        node.querySelector(".stage-count").textContent = PipelineLogic.formatThousands(
          stage.count
        );
        var dot = node.querySelector(".stage-dot");
        dot.className = "stage-dot stage-dot--" + PipelineLogic.statusClass(stage.status);
        dot.setAttribute("title", stage.status);
      });
    }

    function loadSummary() {
      fetchJson("/demo/api/pipeline/summary")
        .then(function (summary) {
          renderKpis(summary.kpis);
          renderStages(summary.stages);
        })
        .catch(function () {
          // Summary refresh failures are non-fatal -- the page keeps
          // showing the last good snapshot rather than clearing the UI.
        });
    }

    function renderEvents(entries) {
      var models = PipelineLogic.buildEventListModel(entries);
      var nowMs = Date.now();

      eventList.textContent = "";
      models.forEach(function (model) {
        var item = document.createElement("li");

        var dot = document.createElement("span");
        dot.className = "event-dot event-dot--" + model.statusClass;

        var body = document.createElement("span");
        body.className = "event-body";

        var time = document.createElement("span");
        time.className = "event-time";
        time.textContent = PipelineLogic.relativeTimeLabel(model.timestamp, nowMs);

        var detail = document.createElement("span");
        detail.className = "event-detail";

        var statusLabel = document.createElement("span");
        statusLabel.className = "event-status-label event-status-label--" + model.statusClass;
        statusLabel.textContent = model.statusLabel;

        detail.appendChild(statusLabel);
        detail.appendChild(document.createTextNode(" — " + model.detail));

        body.appendChild(time);
        body.appendChild(detail);
        item.appendChild(dot);
        item.appendChild(body);
        eventList.appendChild(item);
      });
    }

    function loadEvents() {
      fetchJson("/demo/api/pipeline/events").then(renderEvents).catch(function () {});
    }

    function renderServices(services) {
      var nowMs = Date.now();
      servicesGrid.textContent = "";

      services.forEach(function (service) {
        var card = document.createElement("article");
        card.className = "service-card";
        card.id = "service-" + service.name.toLowerCase();

        var heading = document.createElement("div");
        heading.className = "service-card-heading";

        var name = document.createElement("span");
        name.className = "service-name";
        name.textContent = service.name;

        var dot = document.createElement("span");
        dot.className = "stage-dot stage-dot--" + PipelineLogic.statusClass(service.status);

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
        heartbeatValue.textContent = PipelineLogic.relativeTimeLabel(
          service.last_heartbeat,
          nowMs
        );
        heartbeat.appendChild(heartbeatLabel);
        heartbeat.appendChild(heartbeatValue);

        card.appendChild(heading);
        card.appendChild(latency);
        card.appendChild(heartbeat);
        servicesGrid.appendChild(card);
      });
    }

    function loadServices() {
      fetchJson("/demo/api/pipeline/services").then(renderServices).catch(function () {});
    }

    function upsertLineChart(canvasId, categories, datasets) {
      var canvas = document.getElementById(canvasId);
      if (!canvas || typeof window.Chart === "undefined") {
        return;
      }

      if (charts[canvasId]) {
        charts[canvasId].data.labels = categories;
        charts[canvasId].data.datasets = datasets;
        charts[canvasId].update();
        return;
      }

      charts[canvasId] = new window.Chart(canvas, {
        type: "line",
        data: { labels: categories, datasets: datasets },
        options: {
          animation: { duration: 400 },
          responsive: true,
          scales: {
            x: { ticks: { color: "#8b96a5", maxTicksLimit: 6 }, grid: { color: "rgba(255,255,255,0.05)" } },
            y: { ticks: { color: "#8b96a5" }, grid: { color: "rgba(255,255,255,0.05)" }, beginAtZero: true },
          },
          plugins: { legend: { labels: { color: "#b6c0cc" } } },
        },
      });
    }

    function upsertBarChart(canvasId, categories, values) {
      var canvas = document.getElementById(canvasId);
      if (!canvas || typeof window.Chart === "undefined") {
        return;
      }

      var colors = ["#3b82f6", "#22d3ee", "#a78bfa", "#34d399", "#fbbf24", "#f87171", "#60a5fa", "#f472b6"];
      var dataset = {
        label: "Events",
        data: values,
        backgroundColor: categories.map(function (_, index) {
          return colors[index % colors.length];
        }),
        borderWidth: 0,
      };

      if (charts[canvasId]) {
        charts[canvasId].data.labels = categories;
        charts[canvasId].data.datasets = [dataset];
        charts[canvasId].update();
        return;
      }

      charts[canvasId] = new window.Chart(canvas, {
        type: "bar",
        data: { labels: categories, datasets: [dataset] },
        options: {
          animation: { duration: 400 },
          responsive: true,
          plugins: { legend: { display: false } },
          scales: {
            x: { ticks: { color: "#8b96a5" }, grid: { display: false } },
            y: { ticks: { color: "#8b96a5" }, grid: { color: "rgba(255,255,255,0.05)" }, beginAtZero: true },
          },
        },
      });
    }

    function loadCharts() {
      fetchJson("/demo/api/pipeline/charts")
        .then(function (chartData) {
          upsertLineChart(
            "chart-messages-per-minute",
            chartData.messages_per_minute.categories,
            [PipelineLogic.buildLineDataset("Messages / min", chartData.messages_per_minute.values, "#3b82f6")]
          );
          upsertLineChart(
            "chart-retries",
            chartData.retries_over_time.categories,
            [
              PipelineLogic.buildLineDataset(
                "Retry queue depth",
                chartData.retries_over_time.values,
                PipelineLogic.pickStatusColor("warning")
              ),
            ]
          );
          upsertLineChart(
            "chart-dlq-trend",
            chartData.dlq_trend.categories,
            [
              PipelineLogic.buildLineDataset(
                "DLQ depth",
                chartData.dlq_trend.values,
                PipelineLogic.pickStatusColor("critical")
              ),
            ]
          );
          upsertLineChart(
            "chart-success-failure",
            chartData.success_series.categories,
            [
              PipelineLogic.buildLineDataset(
                "Successful",
                chartData.success_series.values,
                PipelineLogic.pickStatusColor("healthy")
              ),
              PipelineLogic.buildLineDataset(
                "Failed",
                chartData.failure_series.values,
                PipelineLogic.pickStatusColor("critical")
              ),
            ]
          );
          upsertLineChart(
            "chart-latency",
            chartData.latency_ms.categories,
            [PipelineLogic.buildLineDataset("Avg latency (ms)", chartData.latency_ms.values, "#a78bfa")]
          );
          upsertBarChart(
            "chart-event-types",
            chartData.top_event_types.categories,
            chartData.top_event_types.values
          );
        })
        .catch(function () {});
    }

    function renderFlowTimeline(steps) {
      flowTimeline.textContent = "";
      steps.forEach(function (step) {
        var item = document.createElement("li");

        var title = document.createElement("span");
        title.className = "flow-step-title";
        title.textContent = step.label;

        var time = document.createElement("span");
        time.className = "flow-step-time";
        time.textContent = new Date(step.timestamp).toISOString().replace("T", " ").slice(0, 19);

        item.appendChild(title);
        item.appendChild(time);
        flowTimeline.appendChild(item);
      });
    }

    function loadCustomerFlow(customerId) {
      if (!customerId) {
        flowTimeline.textContent = "";
        return;
      }

      fetchJson("/demo/api/pipeline/customer/" + encodeURIComponent(customerId))
        .then(renderFlowTimeline)
        .catch(function () {
          flowTimeline.textContent = "";
          var item = document.createElement("li");
          item.textContent = "Couldn't load this customer's event flow.";
          flowTimeline.appendChild(item);
        });
    }

    function loadCustomerOptions() {
      fetchJson("/demo/api/customers")
        .then(function (customers) {
          if (customers.length === 0) {
            flowHint.textContent = "No demo customers loaded yet — seed them with scripts/seed_demo_customers.py.";
            return;
          }

          flowHint.textContent = customers.length + " customers available.";
          customers.forEach(function (customer) {
            var option = document.createElement("option");
            option.value = customer.customer_id;
            option.textContent =
              customer.first_name + " " + customer.last_name + " (" + customer.customer_id + ")";
            flowSelect.appendChild(option);
          });
        })
        .catch(function () {
          flowHint.textContent = "Couldn't load the customer list.";
        });
    }

    if (flowSelect) {
      flowSelect.addEventListener("change", function () {
        loadCustomerFlow(flowSelect.value);
      });
    }

    // -- Control Center -----------------------------------------------

    var controlBusy = false;
    var buttonAvailability = { replayDisabled: true, retryDisabled: true };

    function applyButtonStates() {
      if (btnReplay) {
        btnReplay.disabled = controlBusy || buttonAvailability.replayDisabled;
      }
      if (btnRetry) {
        btnRetry.disabled = controlBusy || buttonAvailability.retryDisabled;
      }
      [btnGenerate, btnInjectFailure, btnRecover, btnReset].forEach(function (btn) {
        if (btn) {
          btn.disabled = controlBusy;
        }
      });
    }

    function setControlBusy(busy) {
      controlBusy = busy;
      applyButtonStates();
    }

    function syncControlState() {
      fetchJson("/demo/api/pipeline/state")
        .then(function (state) {
          buttonAvailability = PipelineLogic.computeButtonStates(state);
          applyButtonStates();
        })
        .catch(function () {});
    }

    function animateTrace(trace) {
      var schedule = PipelineLogic.stageAnimationSchedule(trace.steps, 450);

      schedule.forEach(function (entry) {
        var node = document.getElementById("stage-" + stageSlug(entry.stage));
        if (!node) {
          return;
        }
        var activeClass =
          "stage-node--active-" + (entry.status === "ok" ? "ok" : entry.status === "pending" ? "pending" : "failed");

        window.setTimeout(function () {
          node.classList.add("stage-node--active", activeClass);
        }, entry.startMs);
        window.setTimeout(function () {
          node.classList.remove("stage-node--active", activeClass);
        }, entry.endMs);
      });

      return schedule.length ? schedule[schedule.length - 1].endMs : 0;
    }

    function refreshAfterAction() {
      loadSummary();
      loadServices();
      loadCharts();
      syncControlState();
    }

    function runControlAction(actionName, requestFn) {
      if (controlBusy) {
        return;
      }
      setControlBusy(true);

      requestFn()
        .then(function (trace) {
          var totalMs = animateTrace(trace);
          if (controlStatus) {
            controlStatus.textContent = PipelineLogic.buildControlStatusMessage(actionName, trace);
          }
          // Derived directly from the trace we already have, rather than
          // waiting on refreshAfterAction()'s async /state re-fetch below --
          // otherwise setControlBusy(false) would briefly re-enable buttons
          // using the *previous* action's availability for one round-trip.
          buttonAvailability = PipelineLogic.computeButtonStates({
            current_event: trace.event,
            has_replayable_event: true,
          });
          window.setTimeout(function () {
            setControlBusy(false);
            refreshAfterAction();
          }, totalMs + 150);
        })
        .catch(function (err) {
          if (controlStatus) {
            controlStatus.textContent = (err && err.message) || "That action couldn't be completed right now.";
          }
          setControlBusy(false);
        });
    }

    if (btnGenerate) {
      btnGenerate.addEventListener("click", function () {
        runControlAction("generate", function () {
          return postJson("/demo/api/pipeline/generate");
        });
      });
    }

    if (btnReplay) {
      btnReplay.addEventListener("click", function () {
        runControlAction("replay", function () {
          return postJson("/demo/api/pipeline/replay");
        });
      });
    }

    if (btnInjectFailure) {
      btnInjectFailure.addEventListener("click", function () {
        var failureType = failureTypeSelect ? failureTypeSelect.value : "consumer_failure";
        runControlAction("failure", function () {
          return postJson("/demo/api/pipeline/failure", { failure_type: failureType });
        });
      });
    }

    if (btnRetry) {
      btnRetry.addEventListener("click", function () {
        runControlAction("retry", function () {
          return postJson("/demo/api/pipeline/retry");
        });
      });
    }

    if (btnRecover) {
      btnRecover.addEventListener("click", function () {
        if (controlBusy) {
          return;
        }
        setControlBusy(true);
        postJson("/demo/api/pipeline/recover")
          .then(function (state) {
            if (controlStatus) {
              controlStatus.textContent =
                "Consumer recovered -- it will process successfully on the next retry.";
            }
            buttonAvailability = PipelineLogic.computeButtonStates(state);
            setControlBusy(false);
            loadServices();
          })
          .catch(function (err) {
            if (controlStatus) {
              controlStatus.textContent = (err && err.message) || "Couldn't recover the consumer right now.";
            }
            setControlBusy(false);
          });
      });
    }

    if (btnReset) {
      btnReset.addEventListener("click", function () {
        if (controlBusy) {
          return;
        }
        setControlBusy(true);
        postJson("/demo/api/pipeline/reset")
          .then(function (state) {
            if (controlStatus) {
              controlStatus.textContent = 'Demo reset -- click "Generate Customer Event" to start again.';
            }
            buttonAvailability = PipelineLogic.computeButtonStates(state);
            setControlBusy(false);
            refreshAfterAction();
          })
          .catch(function (err) {
            if (controlStatus) {
              controlStatus.textContent = (err && err.message) || "Couldn't reset the demo right now.";
            }
            setControlBusy(false);
          });
      });
    }

    syncControlState();

    loadSummary();
    loadEvents();
    loadServices();
    loadCharts();
    loadCustomerOptions();

    window.setInterval(loadSummary, 5000);
    window.setInterval(loadEvents, 3000);
    window.setInterval(loadServices, 8000);
    window.setInterval(loadCharts, 20000);
  });
})();
