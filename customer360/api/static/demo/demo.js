(function () {
  "use strict";

  // ---------------------------------------------------------------------
  // Pure logic (no DOM access below this block) -- kept dependency-free so
  // it can be exercised directly under Node in tests/api/test_demo_js.py,
  // in addition to running in the browser unmodified.
  // ---------------------------------------------------------------------

  function normalize(value) {
    return String(value == null ? "" : value).toLowerCase();
  }

  function customerFullName(customer) {
    return (customer.first_name || "") + " " + (customer.last_name || "");
  }

  function filterCustomers(customers, query) {
    var needle = normalize(query).trim();
    if (!needle) {
      return customers.slice();
    }

    return customers.filter(function (customer) {
      return (
        normalize(customerFullName(customer)).indexOf(needle) !== -1 ||
        normalize(customer.email).indexOf(needle) !== -1 ||
        normalize(customer.customer_id).indexOf(needle) !== -1
      );
    });
  }

  function findCustomerById(customers, customerId) {
    for (var i = 0; i < customers.length; i += 1) {
      if (customers[i].customer_id === customerId) {
        return customers[i];
      }
    }
    return null;
  }

  function deriveStatus(customer) {
    return customer.transaction_count > 0 ? "active" : "dormant";
  }

  function formatCurrency(value) {
    var amount = typeof value === "number" ? value : 0;
    return "$" + amount.toFixed(2);
  }

  function formatDate(isoString) {
    if (!isoString) {
      return "—";
    }
    var date = new Date(isoString);
    if (isNaN(date.getTime())) {
      return "—";
    }
    return date.toISOString().slice(0, 10);
  }

  // Deterministic (not random) small integer hash of the customer ID, so the
  // same fictional customer always produces the same illustrative timeline
  // across page loads -- it never touches a live events/transactions API.
  function hashCustomerId(customerId) {
    var text = String(customerId || "");
    var hash = 0;
    for (var i = 0; i < text.length; i += 1) {
      hash = (hash * 31 + text.charCodeAt(i)) >>> 0;
    }
    return hash;
  }

  var ILLUSTRATIVE_ACTIVITY_TEMPLATE = [
    "Profile created",
    "Email verified",
    "Purchase event received",
    "Support interaction recorded",
  ];

  function buildIllustrativeTimeline(customer) {
    var hash = hashCustomerId(customer.customer_id);
    var anchor = customer.created_at ? new Date(customer.created_at) : new Date();
    if (isNaN(anchor.getTime())) {
      anchor = new Date();
    }

    var entryCount = 2 + (hash % 3); // 2-4 entries, deterministic per customer
    var entries = [];

    for (var i = 0; i < entryCount; i += 1) {
      var label = ILLUSTRATIVE_ACTIVITY_TEMPLATE[i % ILLUSTRATIVE_ACTIVITY_TEMPLATE.length];
      var offsetDays = (hash % 7) * (i + 1) + i;
      var entryDate = new Date(anchor.getTime());
      entryDate.setUTCDate(entryDate.getUTCDate() + offsetDays);

      entries.push({
        label: label,
        date: entryDate.toISOString().slice(0, 10),
      });
    }

    return entries;
  }

  function computeSampleEventsProcessed(totalCustomers, totalTransactions) {
    // Illustrative only: the Kafka pipeline publishes one domain event per
    // profile write, but the API does not currently expose a live event
    // count, so this approximates it from data the API does return.
    return totalTransactions + totalCustomers * 2;
  }

  var DemoLogic = {
    filterCustomers: filterCustomers,
    findCustomerById: findCustomerById,
    deriveStatus: deriveStatus,
    formatCurrency: formatCurrency,
    formatDate: formatDate,
    buildIllustrativeTimeline: buildIllustrativeTimeline,
    computeSampleEventsProcessed: computeSampleEventsProcessed,
    customerFullName: customerFullName,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = DemoLogic;
  }

  // ---------------------------------------------------------------------
  // DOM wiring -- skipped entirely outside a browser (e.g. under Node).
  // ---------------------------------------------------------------------

  if (typeof document === "undefined") {
    return;
  }

  document.addEventListener("DOMContentLoaded", function () {
    var els = {
      summaryTotalCustomers: document.getElementById("summary-total-customers"),
      summaryActiveProfiles: document.getElementById("summary-active-profiles"),
      summaryTotalTransactions: document.getElementById("summary-total-transactions"),
      summaryEventsProcessed: document.getElementById("summary-events-processed"),
      search: document.getElementById("customer-search"),
      searchClear: document.getElementById("search-clear"),
      list: document.getElementById("customer-list"),
      listHint: document.getElementById("list-hint"),
      stateLoading: document.getElementById("state-loading"),
      stateEmpty: document.getElementById("state-empty"),
      stateError: document.getElementById("state-error"),
      stateErrorDetail: document.getElementById("state-error-detail"),
      retryButton: document.getElementById("retry-button"),
      profileEmpty: document.getElementById("profile-empty"),
      profileContent: document.getElementById("profile-content"),
      profileName: document.getElementById("profile-name"),
      profileStatus: document.getElementById("profile-status"),
      profileFields: document.getElementById("profile-fields"),
      activityList: document.getElementById("activity-list"),
    };

    if (!els.list) {
      return;
    }

    var state = {
      customers: [],
      filtered: [],
      selectedId: null,
    };

    function setListState(name) {
      els.stateLoading.classList.toggle("is-hidden", name !== "loading");
      els.stateEmpty.classList.toggle("is-hidden", name !== "empty");
      els.stateError.classList.toggle("is-hidden", name !== "error");
      els.list.classList.toggle("is-hidden", name !== "ready");
      els.listHint.classList.toggle("is-hidden", name !== "ready");
    }

    function renderSummary(summary) {
      els.summaryTotalCustomers.textContent = String(summary.total_customers);
      els.summaryActiveProfiles.textContent = String(summary.active_profiles);
      els.summaryTotalTransactions.textContent = String(summary.total_transactions);
      els.summaryEventsProcessed.textContent = String(
        DemoLogic.computeSampleEventsProcessed(
          summary.total_customers,
          summary.total_transactions
        )
      );
    }

    function renderList() {
      els.list.textContent = "";
      els.listHint.textContent =
        state.filtered.length + " of " + state.customers.length + " customers";

      state.filtered.forEach(function (customer) {
        var item = document.createElement("li");
        item.className = "customer-list-item";
        item.setAttribute("role", "option");
        item.setAttribute("id", "customer-item-" + customer.customer_id);
        item.setAttribute("tabindex", "-1");
        item.setAttribute(
          "aria-selected",
          customer.customer_id === state.selectedId ? "true" : "false"
        );

        var name = document.createElement("span");
        name.className = "item-name";
        name.textContent = DemoLogic.customerFullName(customer);

        var meta = document.createElement("span");
        meta.className = "item-meta";
        meta.textContent = customer.email + " · " + customer.customer_id;

        item.appendChild(name);
        item.appendChild(meta);

        item.addEventListener("click", function () {
          selectCustomer(customer.customer_id);
        });
        item.addEventListener("keydown", function (event) {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            selectCustomer(customer.customer_id);
          }
        });

        els.list.appendChild(item);
      });
    }

    function focusListItem(customerId) {
      var target = document.getElementById("customer-item-" + customerId);
      if (target) {
        target.setAttribute("tabindex", "0");
        target.focus();
      }
    }

    function renderProfile(customer) {
      if (!customer) {
        els.profileEmpty.classList.remove("is-hidden");
        els.profileContent.classList.add("is-hidden");
        return;
      }

      els.profileEmpty.classList.add("is-hidden");
      els.profileContent.classList.remove("is-hidden");

      els.profileName.textContent = DemoLogic.customerFullName(customer);

      var status = DemoLogic.deriveStatus(customer);
      els.profileStatus.textContent = status === "active" ? "Active" : "Dormant";
      els.profileStatus.className =
        "profile-status " + (status === "active" ? "profile-status--active" : "profile-status--dormant");

      var fields = [
        ["Customer ID", customer.customer_id],
        ["Email", customer.email],
        ["City", customer.city || "—"],
        ["State", customer.state || "—"],
        ["Transaction Count", String(customer.transaction_count)],
        ["Total Spend", DemoLogic.formatCurrency(customer.total_spend)],
        ["Avg. Transaction Value", DemoLogic.formatCurrency(customer.average_transaction_value)],
        ["Created", DemoLogic.formatDate(customer.created_at)],
        ["Updated", DemoLogic.formatDate(customer.updated_at)],
      ];

      els.profileFields.textContent = "";
      fields.forEach(function (pair) {
        var dt = document.createElement("dt");
        dt.textContent = pair[0];
        var dd = document.createElement("dd");
        dd.textContent = pair[1];
        els.profileFields.appendChild(dt);
        els.profileFields.appendChild(dd);
      });

      els.activityList.textContent = "";
      DemoLogic.buildIllustrativeTimeline(customer).forEach(function (entry) {
        var li = document.createElement("li");
        var title = document.createElement("span");
        title.className = "activity-title";
        title.textContent = entry.label;
        var date = document.createElement("span");
        date.className = "activity-date";
        date.textContent = entry.date;
        li.appendChild(title);
        li.appendChild(date);
        els.activityList.appendChild(li);
      });
    }

    function selectCustomer(customerId) {
      state.selectedId = customerId;
      renderList();
      focusListItem(customerId);
      renderProfile(DemoLogic.findCustomerById(state.customers, customerId));
    }

    function applySearch() {
      state.filtered = DemoLogic.filterCustomers(state.customers, els.search.value);
      renderList();
    }

    els.search.addEventListener("input", applySearch);

    els.searchClear.addEventListener("click", function () {
      els.search.value = "";
      applySearch();
      els.search.focus();
    });

    els.list.addEventListener("keydown", function (event) {
      if (event.key !== "ArrowDown" && event.key !== "ArrowUp") {
        return;
      }
      event.preventDefault();

      var currentIndex = state.filtered.findIndex(function (customer) {
        return customer.customer_id === state.selectedId;
      });

      var nextIndex;
      if (currentIndex === -1) {
        nextIndex = 0;
      } else if (event.key === "ArrowDown") {
        nextIndex = Math.min(currentIndex + 1, state.filtered.length - 1);
      } else {
        nextIndex = Math.max(currentIndex - 1, 0);
      }

      var nextCustomer = state.filtered[nextIndex];
      if (nextCustomer) {
        selectCustomer(nextCustomer.customer_id);
      }
    });

    els.retryButton.addEventListener("click", function () {
      loadDashboard();
    });

    function fetchJson(url) {
      return fetch(url, { cache: "no-store" }).then(function (response) {
        if (!response.ok) {
          throw new Error("Request to " + url + " failed with " + response.status);
        }
        return response.json();
      });
    }

    function loadDashboard() {
      setListState("loading");
      els.profileEmpty.classList.remove("is-hidden");
      els.profileContent.classList.add("is-hidden");

      Promise.all([fetchJson("/demo/api/summary"), fetchJson("/demo/api/customers")])
        .then(function (results) {
          var summary = results[0];
          var customers = results[1];

          renderSummary(summary);
          state.customers = customers;
          state.filtered = customers;
          state.selectedId = null;

          if (customers.length === 0) {
            setListState("empty");
            return;
          }

          setListState("ready");
          renderList();
        })
        .catch(function (error) {
          els.stateErrorDetail.textContent =
            "The request to the live backend failed: " + error.message;
          setListState("error");
        });
    }

    loadDashboard();
  });
})();
