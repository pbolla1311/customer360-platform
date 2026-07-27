(function () {
  "use strict";

  // ---------------------------------------------------------------------
  // Pure logic (no DOM access below this block) -- exercised directly
  // under Node in tests/api/test_workspace_customers_js.py.
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

  var EDITABLE_FIELDS = ["first_name", "last_name", "email", "city", "state"];

  // Only the fields that actually changed -- keeps the PATCH payload
  // minimal and lets the backend's own diff (email/address/name) decide
  // the resulting event_type without this file needing to duplicate that
  // mapping.
  function diffChangedFields(original, edited) {
    var changed = {};
    EDITABLE_FIELDS.forEach(function (field) {
      var before = original[field] || "";
      var after = (edited[field] || "").trim();
      if (after !== before) {
        changed[field] = after;
      }
    });
    return changed;
  }

  var EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

  function validateEditForm(fields) {
    var errors = {};

    EDITABLE_FIELDS.forEach(function (field) {
      var value = (fields[field] || "").trim();
      if (!value) {
        errors[field] = "Required.";
      }
    });

    if (fields.email && !EMAIL_PATTERN.test(fields.email.trim())) {
      errors.email = "Enter a valid email address.";
    }

    return { valid: Object.keys(errors).length === 0, errors: errors };
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

  function customerHistory(history, customerId) {
    return history.filter(function (entry) {
      return entry.event.customer_id === customerId;
    });
  }

  var CustomersLogic = {
    filterCustomers: filterCustomers,
    findCustomerById: findCustomerById,
    deriveStatus: deriveStatus,
    customerFullName: customerFullName,
    diffChangedFields: diffChangedFields,
    validateEditForm: validateEditForm,
    formatCurrency: formatCurrency,
    formatDate: formatDate,
    customerHistory: customerHistory,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = CustomersLogic;
  }

  // ---------------------------------------------------------------------
  // DOM wiring -- skipped entirely outside a browser (e.g. under Node).
  // ---------------------------------------------------------------------

  if (typeof document === "undefined") {
    return;
  }

  document.addEventListener("DOMContentLoaded", function () {
    var els = {
      search: document.getElementById("ws-customer-search"),
      searchClear: document.getElementById("ws-search-clear"),
      list: document.getElementById("ws-customer-list"),
      listHint: document.getElementById("ws-list-hint"),
      stateLoading: document.getElementById("ws-state-loading"),
      stateEmpty: document.getElementById("ws-state-empty"),
      stateError: document.getElementById("ws-state-error"),
      stateErrorDetail: document.getElementById("ws-state-error-detail"),
      retryButton: document.getElementById("ws-retry-button"),
      profileEmpty: document.getElementById("ws-profile-empty"),
      profileContent: document.getElementById("ws-profile-content"),
      profileName: document.getElementById("ws-profile-name"),
      profileStatus: document.getElementById("ws-profile-status"),
      profileFields: document.getElementById("ws-profile-fields"),
      timeline: document.getElementById("ws-profile-timeline"),
      editForm: document.getElementById("ws-edit-form"),
      editStatus: document.getElementById("ws-edit-status"),
      editSave: document.getElementById("ws-edit-save"),
      editFirstName: document.getElementById("ws-edit-first-name"),
      editLastName: document.getElementById("ws-edit-last-name"),
      editEmail: document.getElementById("ws-edit-email"),
      editCity: document.getElementById("ws-edit-city"),
      editState: document.getElementById("ws-edit-state"),
    };

    if (!els.list || !window.Workspace) {
      return;
    }

    var fetchJson = window.Workspace.fetchJson;
    var patchJson = window.Workspace.patchJson;
    var relativeTimeLabel = window.Workspace.relativeTimeLabel;

    var state = {
      customers: [],
      filtered: [],
      selectedId: null,
      history: [],
      loaded: false,
    };

    function setListState(name) {
      els.stateLoading.classList.toggle("is-hidden", name !== "loading");
      els.stateEmpty.classList.toggle("is-hidden", name !== "empty");
      els.stateError.classList.toggle("is-hidden", name !== "error");
      els.list.classList.toggle("is-hidden", name !== "ready");
      els.listHint.classList.toggle("is-hidden", name !== "ready");
    }

    function renderList() {
      els.list.textContent = "";
      els.listHint.textContent = state.filtered.length + " of " + state.customers.length + " customers";

      state.filtered.forEach(function (customer) {
        var item = document.createElement("li");
        item.className = "customer-list-item";
        item.setAttribute("role", "option");
        item.setAttribute("id", "ws-customer-item-" + customer.customer_id);
        item.setAttribute("tabindex", "-1");
        item.setAttribute("aria-selected", customer.customer_id === state.selectedId ? "true" : "false");

        var name = document.createElement("span");
        name.className = "item-name";
        name.textContent = CustomersLogic.customerFullName(customer);

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

    function populateEditForm(customer) {
      els.editFirstName.value = customer.first_name || "";
      els.editLastName.value = customer.last_name || "";
      els.editEmail.value = customer.email || "";
      els.editCity.value = customer.city || "";
      els.editState.value = customer.state || "";
      els.editStatus.textContent = "";
      els.editStatus.className = "ws-edit-status";
    }

    function renderTimeline(customerId) {
      var entries = CustomersLogic.customerHistory(state.history, customerId);
      els.timeline.textContent = "";

      if (entries.length === 0) {
        var empty = document.createElement("li");
        empty.className = "ws-empty-hint";
        empty.textContent = "No recorded events yet for this customer.";
        els.timeline.appendChild(empty);
        return;
      }

      var nowMs = Date.now();
      entries.forEach(function (entry) {
        var li = document.createElement("li");
        var title = document.createElement("span");
        title.className = "activity-title";
        title.textContent = entry.event.event_type;
        var date = document.createElement("span");
        date.className = "activity-date";
        date.textContent = entry.event.status.toUpperCase() + " · " + relativeTimeLabel(entry.event.created_at, nowMs);
        li.appendChild(title);
        li.appendChild(date);
        els.timeline.appendChild(li);
      });
    }

    function renderProfile(customer) {
      if (!customer) {
        els.profileEmpty.classList.remove("is-hidden");
        els.profileContent.classList.add("is-hidden");
        return;
      }

      els.profileEmpty.classList.add("is-hidden");
      els.profileContent.classList.remove("is-hidden");

      els.profileName.textContent = CustomersLogic.customerFullName(customer);

      var status = CustomersLogic.deriveStatus(customer);
      els.profileStatus.textContent = status === "active" ? "Active" : "Dormant";
      els.profileStatus.className =
        "profile-status " + (status === "active" ? "profile-status--active" : "profile-status--dormant");

      var fields = [
        ["Customer ID", customer.customer_id],
        ["Transaction Count", String(customer.transaction_count)],
        ["Total Spend", CustomersLogic.formatCurrency(customer.total_spend)],
        ["Avg. Transaction Value", CustomersLogic.formatCurrency(customer.average_transaction_value)],
        ["Created", CustomersLogic.formatDate(customer.created_at)],
        ["Updated", CustomersLogic.formatDate(customer.updated_at)],
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

      populateEditForm(customer);
      renderTimeline(customer.customer_id);
    }

    function selectCustomer(customerId) {
      state.selectedId = customerId;
      renderList();
      renderProfile(CustomersLogic.findCustomerById(state.customers, customerId));
    }

    function applySearch() {
      state.filtered = CustomersLogic.filterCustomers(state.customers, els.search.value);
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
      loadCustomers();
    });

    els.editForm.addEventListener("submit", function (event) {
      event.preventDefault();

      var customer = CustomersLogic.findCustomerById(state.customers, state.selectedId);
      if (!customer) {
        return;
      }

      var fields = {
        first_name: els.editFirstName.value,
        last_name: els.editLastName.value,
        email: els.editEmail.value,
        city: els.editCity.value,
        state: els.editState.value,
      };

      var validation = CustomersLogic.validateEditForm(fields);
      if (!validation.valid) {
        els.editStatus.textContent = "Please fill in every field with a valid value.";
        els.editStatus.className = "ws-edit-status ws-edit-status--error";
        return;
      }

      var changed = CustomersLogic.diffChangedFields(customer, fields);
      if (Object.keys(changed).length === 0) {
        els.editStatus.textContent = "No changes to save.";
        els.editStatus.className = "ws-edit-status";
        return;
      }

      els.editSave.disabled = true;
      els.editStatus.textContent = "Saving…";
      els.editStatus.className = "ws-edit-status";

      patchJson("/demo/api/customers/" + encodeURIComponent(customer.customer_id), changed)
        .then(function (result) {
          var index = state.customers.findIndex(function (c) {
            return c.customer_id === customer.customer_id;
          });
          if (index !== -1) {
            state.customers[index] = result.profile;
          }
          state.filtered = CustomersLogic.filterCustomers(state.customers, els.search.value);
          state.history.unshift(result.trace);

          renderList();
          renderProfile(result.profile);

          els.editStatus.textContent =
            result.trace.event.event_type + " → " + result.trace.event.event_id + " (delivered).";
          els.editStatus.className = "ws-edit-status ws-edit-status--ok";
        })
        .catch(function (err) {
          els.editStatus.textContent = (err && err.message) || "Couldn't save this customer right now.";
          els.editStatus.className = "ws-edit-status ws-edit-status--error";
        })
        .then(function () {
          els.editSave.disabled = false;
        });
    });

    function loadCustomers() {
      setListState("loading");
      els.profileEmpty.classList.remove("is-hidden");
      els.profileContent.classList.add("is-hidden");

      Promise.all([fetchJson("/demo/api/customers"), fetchJson("/demo/api/pipeline/history?limit=200")])
        .then(function (results) {
          var customers = results[0];
          var history = results[1];

          state.customers = customers;
          state.filtered = customers;
          state.history = history;
          state.selectedId = null;
          state.loaded = true;

          if (customers.length === 0) {
            setListState("empty");
            return;
          }

          setListState("ready");
          renderList();
        })
        .catch(function (error) {
          els.stateErrorDetail.textContent = "The request to the live backend failed: " + error.message;
          setListState("error");
        });
    }

    window.Workspace.registerView("customers", {
      activate: function () {
        if (!state.loaded) {
          loadCustomers();
        }
      },
      deactivate: function () {},
    });
  });
})();
