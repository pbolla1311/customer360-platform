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

  var PipelineLogic = {
    statusClass: statusClass,
    pickStatusColor: pickStatusColor,
    formatThousands: formatThousands,
    relativeTimeLabel: relativeTimeLabel,
    buildEventListModel: buildEventListModel,
    buildLineDataset: buildLineDataset,
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

    function renderStages(stages) {
      var byName = {};
      stages.forEach(function (stage) {
        byName[stage.name] = stage;
      });

      flowTrack.textContent = "";

      STAGE_ORDER.forEach(function (name, index) {
        var stage = byName[name];
        if (!stage) {
          return;
        }

        var node = document.createElement("div");
        node.className = "stage-node";
        node.id = "stage-" + stageSlug(name);

        var label = document.createElement("span");
        label.className = "stage-name";
        label.textContent = name;

        var count = document.createElement("span");
        count.className = "stage-count";
        count.textContent = PipelineLogic.formatThousands(stage.count);

        var dot = document.createElement("span");
        dot.className = "stage-dot stage-dot--" + PipelineLogic.statusClass(stage.status);
        dot.setAttribute("title", stage.status);

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
