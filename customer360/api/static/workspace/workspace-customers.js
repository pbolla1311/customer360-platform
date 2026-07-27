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
      var tags = (customer.tags || []).join(" ");
      return (
        normalize(customerFullName(customer)).indexOf(needle) !== -1 ||
        normalize(customer.email).indexOf(needle) !== -1 ||
        normalize(customer.customer_id).indexOf(needle) !== -1 ||
        normalize(tags).indexOf(needle) !== -1
      );
    });
  }

  // customer.status is the real, persisted lifecycle field ("active" |
  // "archived") -- distinct from deriveStatus() below, which is a
  // transaction-activity signal, not a lifecycle one.
  function filterByCustomerStatus(customers, statusFilter) {
    if (!statusFilter || statusFilter === "all") {
      return customers.slice();
    }
    return customers.filter(function (customer) {
      return (customer.status || "active") === statusFilter;
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
  // minimal and lets the backend's own diff (email/address/status/name)
  // decide the resulting event_type without this file needing to
  // duplicate that mapping. Tags are diffed separately (list, not a
  // plain string) by diffTags() below; status changes go through the
  // dedicated archive/restore action, not this form.
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

  function parseTagsInput(rawInput) {
    return String(rawInput || "")
      .split(",")
      .map(function (tag) {
        return tag.trim();
      })
      .filter(function (tag) {
        return tag.length > 0;
      });
  }

  function tagsEqual(a, b) {
    var sortedA = a.slice().sort();
    var sortedB = b.slice().sort();
    if (sortedA.length !== sortedB.length) {
      return false;
    }
    for (var i = 0; i < sortedA.length; i += 1) {
      if (sortedA[i] !== sortedB[i]) {
        return false;
      }
    }
    return true;
  }

  // Returns a { tags: [...] } fragment to merge into a PATCH payload, or
  // null when the parsed tag list is unchanged from the customer's current
  // tags (order/duplicates ignored -- the backend already dedupes/sorts).
  function diffTags(customer, rawInput) {
    var parsed = parseTagsInput(rawInput);
    if (tagsEqual(customer.tags || [], parsed)) {
      return null;
    }
    return { tags: parsed };
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

  function customerAuditEntries(history, customerId) {
    return customerHistory(history, customerId).filter(function (entry) {
      return !!entry.audit;
    });
  }

  function latestTraceForCustomer(history, customerId) {
    var entries = customerHistory(history, customerId);
    return entries.length > 0 ? entries[0] : null;
  }

  // Aggregate-only: this schema stores rolled-up totals per customer, not
  // a per-order ledger, so "Orders" is an honest relabeling of those
  // totals, never fabricated per-order rows.
  function aggregateOrderMetrics(customer) {
    return {
      totalOrders: customer.transaction_count || 0,
      totalValue: customer.total_spend || 0,
      avgOrderValue: customer.average_transaction_value || 0,
    };
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  // Bounded 0-100, derived (never sent to the backend, never stored):
  // up to 50 points from lifetime spend, 30 from transaction frequency,
  // 20 from recency of the last update. Deterministic given `nowMs` so
  // it's reproducible in tests instead of depending on Date.now().
  function computeCustomerScore(customer, nowMs) {
    var spendScore = clamp((customer.total_spend || 0) / 5000, 0, 1) * 50;
    var frequencyScore = clamp((customer.transaction_count || 0) / 40, 0, 1) * 30;

    var recencyScore = 0;
    if (customer.updated_at) {
      var updatedMs = new Date(customer.updated_at).getTime();
      if (!isNaN(updatedMs)) {
        var ageDays = Math.max(0, (nowMs - updatedMs) / 86400000);
        recencyScore = clamp(20 - (ageDays / 365) * 20, 0, 20);
      }
    }

    return Math.round(clamp(spendScore + frequencyScore + recencyScore, 0, 100));
  }

  function paginate(items, page, pageSize) {
    var size = pageSize > 0 ? pageSize : items.length || 1;
    var totalItems = items.length;
    var totalPages = Math.max(1, Math.ceil(totalItems / size));
    var safePage = clamp(page || 1, 1, totalPages);
    var start = (safePage - 1) * size;

    return {
      items: items.slice(start, start + size),
      page: safePage,
      pageSize: size,
      totalItems: totalItems,
      totalPages: totalPages,
    };
  }

  var CustomersLogic = {
    filterCustomers: filterCustomers,
    filterByCustomerStatus: filterByCustomerStatus,
    findCustomerById: findCustomerById,
    deriveStatus: deriveStatus,
    customerFullName: customerFullName,
    diffChangedFields: diffChangedFields,
    parseTagsInput: parseTagsInput,
    diffTags: diffTags,
    validateEditForm: validateEditForm,
    formatCurrency: formatCurrency,
    formatDate: formatDate,
    customerHistory: customerHistory,
    customerAuditEntries: customerAuditEntries,
    latestTraceForCustomer: latestTraceForCustomer,
    aggregateOrderMetrics: aggregateOrderMetrics,
    computeCustomerScore: computeCustomerScore,
    paginate: paginate,
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
      statusFilter: document.getElementById("ws-status-filter"),
      list: document.getElementById("ws-customer-list"),
      listHint: document.getElementById("ws-list-hint"),
      pagination: document.getElementById("ws-pagination"),
      pagePrev: document.getElementById("ws-page-prev"),
      pageNext: document.getElementById("ws-page-next"),
      pageIndicator: document.getElementById("ws-page-indicator"),
      stateLoading: document.getElementById("ws-state-loading"),
      stateEmpty: document.getElementById("ws-state-empty"),
      stateError: document.getElementById("ws-state-error"),
      stateErrorDetail: document.getElementById("ws-state-error-detail"),
      retryButton: document.getElementById("ws-retry-button"),
      profileEmpty: document.getElementById("ws-profile-empty"),
      profileContent: document.getElementById("ws-profile-content"),
      profileName: document.getElementById("ws-profile-name"),
      profileStatus: document.getElementById("ws-profile-status"),
      profileScore: document.getElementById("ws-profile-score"),
      profileTags: document.getElementById("ws-profile-tags"),
      profileFields: document.getElementById("ws-profile-fields"),
      profileOrders: document.getElementById("ws-profile-orders"),
      timeline: document.getElementById("ws-profile-timeline"),
      eventsBody: document.getElementById("ws-profile-events-body"),
      auditList: document.getElementById("ws-profile-audit-list"),
      traceCaption: document.getElementById("ws-profile-trace-caption"),
      traceSteps: document.getElementById("ws-profile-trace-steps"),
      archiveToggle: document.getElementById("ws-archive-toggle"),
      archiveStatus: document.getElementById("ws-archive-status"),
      editForm: document.getElementById("ws-edit-form"),
      editStatus: document.getElementById("ws-edit-status"),
      editSave: document.getElementById("ws-edit-save"),
      editFirstName: document.getElementById("ws-edit-first-name"),
      editLastName: document.getElementById("ws-edit-last-name"),
      editEmail: document.getElementById("ws-edit-email"),
      editCity: document.getElementById("ws-edit-city"),
      editState: document.getElementById("ws-edit-state"),
      editTags: document.getElementById("ws-edit-tags"),
      tabs: Array.prototype.slice.call(document.querySelectorAll(".ws-tab")),
      tabPanels: Array.prototype.slice.call(document.querySelectorAll(".ws-tab-panel")),
    };

    if (!els.list || !window.Workspace) {
      return;
    }

    var fetchJson = window.Workspace.fetchJson;
    var patchJson = window.Workspace.patchJson;
    var relativeTimeLabel = window.Workspace.relativeTimeLabel;
    var PAGE_SIZE = 10;

    var state = {
      customers: [],
      filtered: [],
      selectedId: null,
      history: [],
      loaded: false,
      page: 1,
      statusFilter: "all",
    };

    function setListState(name) {
      els.stateLoading.classList.toggle("is-hidden", name !== "loading");
      els.stateEmpty.classList.toggle("is-hidden", name !== "empty");
      els.stateError.classList.toggle("is-hidden", name !== "error");
      els.list.classList.toggle("is-hidden", name !== "ready");
      els.listHint.classList.toggle("is-hidden", name !== "ready");
      els.pagination.classList.toggle("is-hidden", name !== "ready");
    }

    function currentPageSlice() {
      return CustomersLogic.paginate(state.filtered, state.page, PAGE_SIZE);
    }

    function renderList() {
      var pageResult = currentPageSlice();
      state.page = pageResult.page;

      els.list.textContent = "";
      els.listHint.textContent = state.filtered.length + " of " + state.customers.length + " customers";
      els.pageIndicator.textContent = "Page " + pageResult.page + " of " + pageResult.totalPages;
      els.pagePrev.disabled = pageResult.page <= 1;
      els.pageNext.disabled = pageResult.page >= pageResult.totalPages;

      pageResult.items.forEach(function (customer) {
        var item = document.createElement("li");
        item.className = "customer-list-item";
        item.setAttribute("role", "option");
        item.setAttribute("id", "ws-customer-item-" + customer.customer_id);
        item.setAttribute("tabindex", "-1");
        item.setAttribute("aria-selected", customer.customer_id === state.selectedId ? "true" : "false");

        var name = document.createElement("span");
        name.className = "item-name";
        name.textContent =
          CustomersLogic.customerFullName(customer) +
          ((customer.status || "active") === "archived" ? " (Archived)" : "");

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
      els.editTags.value = (customer.tags || []).join(", ");
      els.editStatus.textContent = "";
      els.editStatus.className = "ws-edit-status";
    }

    function renderTags(tags) {
      els.profileTags.textContent = "";
      (tags || []).forEach(function (tag) {
        var chip = document.createElement("span");
        chip.className = "ws-tag-chip";
        chip.textContent = tag;
        els.profileTags.appendChild(chip);
      });
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

    function renderOrders(customer) {
      var metrics = CustomersLogic.aggregateOrderMetrics(customer);
      var fields = [
        ["Total Orders", String(metrics.totalOrders)],
        ["Total Value", CustomersLogic.formatCurrency(metrics.totalValue)],
        ["Avg. Order Value", CustomersLogic.formatCurrency(metrics.avgOrderValue)],
      ];
      els.profileOrders.textContent = "";
      fields.forEach(function (pair) {
        var dt = document.createElement("dt");
        dt.textContent = pair[0];
        var dd = document.createElement("dd");
        dd.textContent = pair[1];
        els.profileOrders.appendChild(dt);
        els.profileOrders.appendChild(dd);
      });
    }

    function renderEventsTab(customerId) {
      var entries = CustomersLogic.customerHistory(state.history, customerId);
      els.eventsBody.textContent = "";

      if (entries.length === 0 || !window.PipelineViewLogic) {
        var row = document.createElement("tr");
        var cell = document.createElement("td");
        cell.colSpan = 6;
        cell.className = "ws-empty-hint";
        cell.textContent = "No events yet for this customer.";
        row.appendChild(cell);
        els.eventsBody.appendChild(row);
        return;
      }

      var nowMs = Date.now();
      var pipelineLogic = window.PipelineViewLogic;
      entries.forEach(function (entry) {
        var event = entry.event;
        var tr = document.createElement("tr");

        var typeTd = document.createElement("td");
        typeTd.textContent = event.event_type;
        tr.appendChild(typeTd);

        var statusTd = document.createElement("td");
        var pill = document.createElement("span");
        pill.className = "ws-status-pill " + pipelineLogic.statusPillClass(event.status);
        pill.textContent = event.status.toUpperCase();
        statusTd.appendChild(pill);
        tr.appendChild(statusTd);

        var stageTd = document.createElement("td");
        stageTd.textContent = pipelineLogic.deriveStageLabel(event.status);
        tr.appendChild(stageTd);

        var retryTd = document.createElement("td");
        retryTd.textContent = String(event.retry_count);
        tr.appendChild(retryTd);

        var corrTd = document.createElement("td");
        corrTd.textContent = event.correlation_id || "—";
        tr.appendChild(corrTd);

        var timeTd = document.createElement("td");
        timeTd.textContent = relativeTimeLabel(event.created_at, nowMs);
        tr.appendChild(timeTd);

        els.eventsBody.appendChild(tr);
      });
    }

    function renderAuditTab(customerId) {
      var entries = CustomersLogic.customerAuditEntries(state.history, customerId);
      els.auditList.textContent = "";

      if (entries.length === 0) {
        var empty = document.createElement("li");
        empty.className = "ws-empty-hint";
        empty.textContent = "No audited changes yet for this customer.";
        els.auditList.appendChild(empty);
        return;
      }

      var nowMs = Date.now();
      entries.forEach(function (entry) {
        var li = document.createElement("li");

        var heading = document.createElement("div");
        heading.className = "ws-audit-entry-heading";
        var title = document.createElement("span");
        title.className = "ws-item-title";
        title.textContent = entry.audit.actor + " changed " + entry.audit.changes.join(", ");
        var meta = document.createElement("span");
        meta.className = "ws-item-meta";
        meta.textContent = relativeTimeLabel(entry.event.created_at, nowMs);
        heading.appendChild(title);
        heading.appendChild(meta);

        var details = document.createElement("p");
        details.className = "ws-panel-note";
        details.textContent = entry.audit.changes
          .map(function (field) {
            return field + ': "' + entry.audit.before[field] + '" -> "' + entry.audit.after[field] + '"';
          })
          .join("; ");

        li.appendChild(heading);
        li.appendChild(details);
        els.auditList.appendChild(li);
      });
    }

    function renderTraceTab(customerId) {
      var latest = CustomersLogic.latestTraceForCustomer(state.history, customerId);
      els.traceSteps.textContent = "";

      if (!latest || !window.PipelineViewLogic) {
        els.traceCaption.textContent = "No events yet for this customer.";
        return;
      }

      els.traceCaption.textContent =
        "Most recent event: " + latest.event.event_type + " (" + latest.event.event_id + ")";

      var pipelineLogic = window.PipelineViewLogic;
      latest.steps.forEach(function (step) {
        var stepEl = document.createElement("li");
        stepEl.className = "ws-audit-step " + pipelineLogic.stepChipClass(step.status);
        stepEl.textContent = step.stage + " (" + step.status + ", " + step.processing_time_ms.toFixed(1) + " ms)";
        els.traceSteps.appendChild(stepEl);
      });
    }

    function updateArchiveToggle(customer) {
      var isArchived = (customer.status || "active") === "archived";
      els.archiveToggle.textContent = isArchived ? "Restore Customer" : "Archive Customer";
      els.archiveToggle.className = "btn " + (isArchived ? "btn-primary" : "btn-secondary");
      els.archiveStatus.textContent = "";
      els.archiveStatus.className = "ws-edit-status";
    }

    function activateTab(tabName) {
      els.tabs.forEach(function (tab) {
        var isActive = tab.getAttribute("data-tab") === tabName;
        tab.classList.toggle("is-active", isActive);
        tab.setAttribute("aria-selected", isActive ? "true" : "false");
      });
      els.tabPanels.forEach(function (panel) {
        panel.classList.toggle("is-hidden", panel.getAttribute("data-tab-panel") !== tabName);
      });
    }

    els.tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        activateTab(tab.getAttribute("data-tab"));
      });
    });

    function renderProfile(customer) {
      if (!customer) {
        els.profileEmpty.classList.remove("is-hidden");
        els.profileContent.classList.add("is-hidden");
        return;
      }

      els.profileEmpty.classList.add("is-hidden");
      els.profileContent.classList.remove("is-hidden");

      els.profileName.textContent = CustomersLogic.customerFullName(customer);

      var isArchived = (customer.status || "active") === "archived";
      els.profileStatus.textContent = isArchived ? "Archived" : "Active";
      els.profileStatus.className =
        "profile-status " + (isArchived ? "profile-status--archived" : "profile-status--active");

      var score = CustomersLogic.computeCustomerScore(customer, Date.now());
      els.profileScore.textContent = "Score: " + score + "/100";

      renderTags(customer.tags);

      var fields = [
        ["Customer ID", customer.customer_id],
        ["Engagement", CustomersLogic.deriveStatus(customer) === "active" ? "Active (has transactions)" : "Dormant"],
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

      updateArchiveToggle(customer);
      populateEditForm(customer);
      renderTimeline(customer.customer_id);
      renderOrders(customer);
      renderEventsTab(customer.customer_id);
      renderAuditTab(customer.customer_id);
      renderTraceTab(customer.customer_id);
    }

    function selectCustomer(customerId) {
      state.selectedId = customerId;
      activateTab("overview");
      renderList();
      renderProfile(CustomersLogic.findCustomerById(state.customers, customerId));
      // Deep-linkable URL for sharing/reload, via replaceState (not
      // location.hash) specifically so it does NOT fire a hashchange --
      // the view isn't changing, just which customer is selected within it.
      if (window.history && window.history.replaceState) {
        window.history.replaceState(null, "", "#/customers/" + encodeURIComponent(customerId));
      }
    }

    // Selects the customer named in "#/customers/{id}" -- reached either
    // by a direct/shared URL, or by a Global Search result (which sets
    // location.hash and so goes through the normal router).
    function selectCustomerFromHashIfPresent() {
      var param = window.Workspace.getHashParam ? window.Workspace.getHashParam() : "";
      if (param && CustomersLogic.findCustomerById(state.customers, param)) {
        selectCustomer(param);
      }
    }

    function applyFilters() {
      var byStatus = CustomersLogic.filterByCustomerStatus(state.customers, state.statusFilter);
      state.filtered = CustomersLogic.filterCustomers(byStatus, els.search.value);
      state.page = 1;
      renderList();
    }

    els.search.addEventListener("input", applyFilters);

    els.statusFilter.addEventListener("change", function () {
      state.statusFilter = els.statusFilter.value;
      applyFilters();
    });

    els.searchClear.addEventListener("click", function () {
      els.search.value = "";
      applyFilters();
      els.search.focus();
    });

    els.pagePrev.addEventListener("click", function () {
      state.page = Math.max(1, state.page - 1);
      renderList();
    });

    els.pageNext.addEventListener("click", function () {
      state.page = state.page + 1;
      renderList();
    });

    els.list.addEventListener("keydown", function (event) {
      if (event.key !== "ArrowDown" && event.key !== "ArrowUp") {
        return;
      }
      event.preventDefault();

      var pageItems = currentPageSlice().items;
      var currentIndex = pageItems.findIndex(function (customer) {
        return customer.customer_id === state.selectedId;
      });

      var nextIndex;
      if (currentIndex === -1) {
        nextIndex = 0;
      } else if (event.key === "ArrowDown") {
        nextIndex = Math.min(currentIndex + 1, pageItems.length - 1);
      } else {
        nextIndex = Math.max(currentIndex - 1, 0);
      }

      var nextCustomer = pageItems[nextIndex];
      if (nextCustomer) {
        selectCustomer(nextCustomer.customer_id);
      }
    });

    els.retryButton.addEventListener("click", function () {
      loadCustomers();
    });

    function applyUpdateResult(result) {
      var index = state.customers.findIndex(function (c) {
        return c.customer_id === result.profile.customer_id;
      });
      if (index !== -1) {
        state.customers[index] = result.profile;
      }
      applyFilters();
      renderProfile(result.profile);
      state.history.unshift(result.trace);
    }

    els.archiveToggle.addEventListener("click", function () {
      var customer = CustomersLogic.findCustomerById(state.customers, state.selectedId);
      if (!customer) {
        return;
      }

      var nextStatus = (customer.status || "active") === "archived" ? "active" : "archived";
      els.archiveToggle.disabled = true;
      els.archiveStatus.textContent = nextStatus === "archived" ? "Archiving…" : "Restoring…";
      els.archiveStatus.className = "ws-edit-status";

      patchJson("/demo/api/customers/" + encodeURIComponent(customer.customer_id), {
        status: nextStatus,
      })
        .then(function (result) {
          applyUpdateResult(result);
          els.archiveStatus.textContent =
            result.trace.event.event_type + " → " + result.trace.event.event_id + " (delivered).";
          els.archiveStatus.className = "ws-edit-status ws-edit-status--ok";
        })
        .catch(function (err) {
          els.archiveStatus.textContent = (err && err.message) || "Couldn't update this customer right now.";
          els.archiveStatus.className = "ws-edit-status ws-edit-status--error";
        })
        .then(function () {
          els.archiveToggle.disabled = false;
        });
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
      var tagsDiff = CustomersLogic.diffTags(customer, els.editTags.value);
      if (tagsDiff) {
        changed.tags = tagsDiff.tags;
      }

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
          applyUpdateResult(result);
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
          state.history = history;
          state.selectedId = null;
          state.loaded = true;
          applyFilters();

          if (customers.length === 0) {
            setListState("empty");
            return;
          }

          setListState("ready");
          selectCustomerFromHashIfPresent();
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
        } else {
          selectCustomerFromHashIfPresent();
        }
      },
      deactivate: function () {},
    });
  });
})();
