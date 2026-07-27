(function () {
  "use strict";

  // ---------------------------------------------------------------------
  // Pure logic (no DOM access below this block) -- exercised directly
  // under Node in tests/api/test_workspace_analytics_js.py. All of these
  // aggregate the same /demo/api/customers rows the Customers view already
  // fetches -- no new backend endpoint, just client-side aggregation of
  // real data (matching demo.js's existing convention of doing this kind
  // of derived-metric computation in the browser).
  // ---------------------------------------------------------------------

  function sumTotalSpend(customers) {
    return customers.reduce(function (sum, c) {
      return sum + (c.total_spend || 0);
    }, 0);
  }

  function sumTransactions(customers) {
    return customers.reduce(function (sum, c) {
      return sum + (c.transaction_count || 0);
    }, 0);
  }

  function averageOrderValue(customers) {
    var transactions = sumTransactions(customers);
    if (transactions === 0) {
      return 0;
    }
    return sumTotalSpend(customers) / transactions;
  }

  function groupByState(customers) {
    var counts = {};
    customers.forEach(function (c) {
      var key = c.state || "Unknown";
      counts[key] = (counts[key] || 0) + 1;
    });

    var entries = Object.keys(counts).map(function (key) {
      return [key, counts[key]];
    });
    entries.sort(function (a, b) {
      return b[1] - a[1];
    });

    return {
      categories: entries.map(function (e) {
        return e[0];
      }),
      values: entries.map(function (e) {
        return e[1];
      }),
    };
  }

  // ISO-8601 week number, deterministic given a Date -- used only to
  // bucket signups into "Customer Growth" chart categories.
  function isoWeekKey(date) {
    var target = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()));
    var dayNumber = (target.getUTCDay() + 6) % 7;
    target.setUTCDate(target.getUTCDate() - dayNumber + 3);
    var firstThursday = new Date(Date.UTC(target.getUTCFullYear(), 0, 4));
    var week =
      1 +
      Math.round(
        ((target.getTime() - firstThursday.getTime()) / 86400000 - 3 + ((firstThursday.getUTCDay() + 6) % 7)) / 7
      );
    return target.getUTCFullYear() + "-W" + (week < 10 ? "0" + week : week);
  }

  function growthByWeek(customers) {
    var counts = {};
    customers.forEach(function (c) {
      if (!c.created_at) {
        return;
      }
      var date = new Date(c.created_at);
      if (isNaN(date.getTime())) {
        return;
      }
      var key = isoWeekKey(date);
      counts[key] = (counts[key] || 0) + 1;
    });

    var keys = Object.keys(counts).sort();
    return {
      categories: keys,
      values: keys.map(function (key) {
        return counts[key];
      }),
    };
  }

  // customer.status defaults to "active" for any row that predates the
  // status column -- never silently excludes older data.
  function nonArchivedCustomers(customers) {
    return customers.filter(function (c) {
      return (c.status || "active") !== "archived";
    });
  }

  // Derived, not stored: average lifetime spend across non-archived
  // customers -- the honest proxy available in a schema with rolled-up
  // totals instead of a full order history.
  function averageCustomerLifetimeValue(customers) {
    var active = nonArchivedCustomers(customers);
    if (active.length === 0) {
      return 0;
    }
    return sumTotalSpend(active) / active.length;
  }

  // Distinct from Overview's "Active Profiles" (transaction_count > 0
  // over ALL customers): this also excludes archived customers, since an
  // executive "active customers" figure shouldn't count accounts that
  // have been archived even if they have historical transactions.
  function countActiveCustomers(customers) {
    return customers.filter(function (c) {
      return (c.status || "active") !== "archived" && (c.transaction_count || 0) > 0;
    }).length;
  }

  function pipelineSuccessRate(kpis) {
    if (!kpis || !kpis.messages_processed) {
      return 0;
    }
    return (kpis.successful_events / kpis.messages_processed) * 100;
  }

  function topCustomers(customers, limit) {
    return customers
      .slice()
      .sort(function (a, b) {
        return (b.total_spend || 0) - (a.total_spend || 0);
      })
      .slice(0, limit || 10);
  }

  function formatCurrency(value) {
    var amount = typeof value === "number" && !isNaN(value) ? value : 0;
    return "$" + amount.toFixed(2);
  }

  var AnalyticsLogic = {
    sumTotalSpend: sumTotalSpend,
    sumTransactions: sumTransactions,
    averageOrderValue: averageOrderValue,
    groupByState: groupByState,
    growthByWeek: growthByWeek,
    isoWeekKey: isoWeekKey,
    topCustomers: topCustomers,
    formatCurrency: formatCurrency,
    nonArchivedCustomers: nonArchivedCustomers,
    averageCustomerLifetimeValue: averageCustomerLifetimeValue,
    countActiveCustomers: countActiveCustomers,
    pipelineSuccessRate: pipelineSuccessRate,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = AnalyticsLogic;
  }

  // ---------------------------------------------------------------------
  // DOM wiring -- skipped entirely outside a browser (e.g. under Node).
  // ---------------------------------------------------------------------

  if (typeof document === "undefined") {
    return;
  }

  // Exposed so workspace.js's Overview "Customer Growth" sparkline can
  // reuse the same ISO-week bucketing instead of duplicating it -- see
  // the identical window.PipelineViewLogic export in workspace-pipeline.js
  // for why script load order doesn't matter here.
  window.AnalyticsLogic = AnalyticsLogic;

  document.addEventListener("DOMContentLoaded", function () {
    if (!window.Workspace) {
      return;
    }

    var fetchJson = window.Workspace.fetchJson;
    var animateValue = window.Workspace.animateValue;
    var charts = {};

    function upsertLineChart(canvasId, categories, dataset) {
      var canvas = document.getElementById(canvasId);
      if (!canvas || typeof window.Chart === "undefined") {
        return;
      }
      if (charts[canvasId]) {
        charts[canvasId].data.labels = categories;
        charts[canvasId].data.datasets = [dataset];
        charts[canvasId].update();
        return;
      }
      charts[canvasId] = new window.Chart(canvas, {
        type: "line",
        data: { labels: categories, datasets: [dataset] },
        options: {
          animation: { duration: 400 },
          responsive: true,
          scales: {
            x: { ticks: { color: "#8b96a5", maxTicksLimit: 8 }, grid: { color: "rgba(255,255,255,0.05)" } },
            y: { ticks: { color: "#8b96a5" }, grid: { color: "rgba(255,255,255,0.05)" }, beginAtZero: true },
          },
          plugins: { legend: { labels: { color: "#b6c0cc" } } },
        },
      });
    }

    function upsertBarChart(canvasId, categories, values, colors) {
      var canvas = document.getElementById(canvasId);
      if (!canvas || typeof window.Chart === "undefined") {
        return;
      }
      var dataset = {
        label: "Count",
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

    var CATEGORICAL_COLORS = ["#3b82f6", "#22d3ee", "#a78bfa", "#34d399", "#fbbf24", "#f87171", "#60a5fa", "#f472b6"];

    var kpiRevenue = document.getElementById("an-kpi-revenue");
    var kpiTransactions = document.getElementById("an-kpi-transactions");
    var kpiAov = document.getElementById("an-kpi-aov");
    var kpiCustomers = document.getElementById("an-kpi-customers");
    var kpiClv = document.getElementById("an-kpi-clv");
    var kpiActiveCustomers = document.getElementById("an-kpi-active-customers");
    var kpiSuccessRate = document.getElementById("an-kpi-success-rate");
    var kpiPipelineThroughput = document.getElementById("an-kpi-pipeline-throughput");
    var topCustomersBody = document.getElementById("an-top-customers-body");

    function renderTopCustomers(customers) {
      if (!topCustomersBody) {
        return;
      }
      var rows = AnalyticsLogic.topCustomers(customers, 10);
      topCustomersBody.textContent = "";

      if (rows.length === 0) {
        var tr = document.createElement("tr");
        var td = document.createElement("td");
        td.colSpan = 5;
        td.className = "ws-empty-hint";
        td.textContent = "No customers loaded yet.";
        tr.appendChild(td);
        topCustomersBody.appendChild(tr);
        return;
      }

      rows.forEach(function (customer) {
        var row = document.createElement("tr");
        [
          (customer.first_name || "") + " " + (customer.last_name || ""),
          customer.city || "—",
          customer.state || "—",
          String(customer.transaction_count),
          AnalyticsLogic.formatCurrency(customer.total_spend),
        ].forEach(function (text) {
          var cell = document.createElement("td");
          cell.textContent = text;
          row.appendChild(cell);
        });
        topCustomersBody.appendChild(row);
      });
    }

    function loadAnalytics() {
      Promise.all([
        fetchJson("/demo/api/customers"),
        fetchJson("/demo/api/pipeline/charts"),
        fetchJson("/demo/api/pipeline/summary"),
      ])
        .then(function (results) {
          var customers = results[0];
          var pipelineCharts = results[1];
          var pipelineSummary = results[2];

          animateValue(kpiRevenue, AnalyticsLogic.sumTotalSpend(customers), AnalyticsLogic.formatCurrency);
          animateValue(kpiTransactions, AnalyticsLogic.sumTransactions(customers), function (v) {
            return String(Math.round(v));
          });
          animateValue(kpiAov, AnalyticsLogic.averageOrderValue(customers), AnalyticsLogic.formatCurrency);
          animateValue(kpiCustomers, customers.length, function (v) {
            return String(Math.round(v));
          });
          animateValue(
            kpiClv,
            AnalyticsLogic.averageCustomerLifetimeValue(customers),
            AnalyticsLogic.formatCurrency
          );
          animateValue(kpiActiveCustomers, AnalyticsLogic.countActiveCustomers(customers), function (v) {
            return String(Math.round(v));
          });
          animateValue(
            kpiSuccessRate,
            AnalyticsLogic.pipelineSuccessRate(pipelineSummary.kpis),
            function (v) {
              return v.toFixed(1);
            }
          );
          animateValue(kpiPipelineThroughput, pipelineSummary.kpis.events_per_sec, function (v) {
            return v.toFixed(2);
          });

          var growth = AnalyticsLogic.growthByWeek(customers);
          upsertLineChart("an-chart-growth", growth.categories, {
            label: "New customers",
            data: growth.values,
            borderColor: "#22d3ee",
            backgroundColor: "#22d3ee33",
            tension: 0.35,
            fill: true,
            pointRadius: 2,
            borderWidth: 2,
          });

          var states = AnalyticsLogic.groupByState(customers);
          upsertBarChart("an-chart-states", states.categories, states.values, CATEGORICAL_COLORS);

          upsertBarChart(
            "an-chart-events",
            pipelineCharts.top_event_types.categories,
            pipelineCharts.top_event_types.values,
            CATEGORICAL_COLORS
          );

          renderTopCustomers(customers);
        })
        .catch(function () {});
    }

    window.Workspace.registerView("analytics", {
      activate: function () {
        loadAnalytics();
      },
      deactivate: function () {},
    });
  });
})();
