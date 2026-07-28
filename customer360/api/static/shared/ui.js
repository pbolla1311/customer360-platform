(function () {
  "use strict";

  // ---------------------------------------------------------------------
  // Pure logic (no DOM access below this block) -- exercised directly
  // under Node in tests/api/test_ui_js.py.
  // ---------------------------------------------------------------------

  var TOAST_ICONS = {
    success: "✓",
    error: "✕",
    info: "ℹ",
  };

  function toastIconFor(type) {
    return TOAST_ICONS[type] || TOAST_ICONS.info;
  }

  var UILogic = {
    toastIconFor: toastIconFor,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = UILogic;
  }

  // ---------------------------------------------------------------------
  // DOM wiring -- skipped entirely outside a browser (e.g. under Node).
  // ---------------------------------------------------------------------

  if (typeof document === "undefined") {
    return;
  }

  var TOAST_DURATION_MS = 4000;

  function ensureToastContainer() {
    var container = document.getElementById("ui-toast-container");
    if (!container) {
      container = document.createElement("div");
      container.id = "ui-toast-container";
      container.className = "toast-container";
      container.setAttribute("role", "status");
      container.setAttribute("aria-live", "polite");
      document.body.appendChild(container);
    }
    return container;
  }

  function toast(message, options) {
    var opts = options || {};
    var type = opts.type || "info";
    var container = ensureToastContainer();

    var el = document.createElement("div");
    el.className = "toast toast--" + type;

    var icon = document.createElement("span");
    icon.className = "toast__icon";
    icon.textContent = UILogic.toastIconFor(type);
    icon.setAttribute("aria-hidden", "true");

    var text = document.createElement("span");
    text.textContent = message;

    el.appendChild(icon);
    el.appendChild(text);
    container.appendChild(el);

    var remove = function () {
      el.classList.add("is-leaving");
      window.setTimeout(function () {
        if (el.parentNode) {
          el.parentNode.removeChild(el);
        }
      }, 220);
    };

    window.setTimeout(remove, TOAST_DURATION_MS);
    el.addEventListener("click", remove);

    return el;
  }

  var activeModal = null;

  function closeModal(overlay, resolve, result, previouslyFocused) {
    if (activeModal === overlay) {
      activeModal = null;
    }
    if (overlay.parentNode) {
      overlay.parentNode.removeChild(overlay);
    }
    document.removeEventListener("keydown", overlay._onKeydown);
    if (previouslyFocused && typeof previouslyFocused.focus === "function") {
      previouslyFocused.focus();
    }
    resolve(result);
  }

  var modalIdCounter = 0;

  function confirmModal(options) {
    var opts = options || {};
    var title = opts.title || "Are you sure?";
    var body = opts.body || "";
    var confirmLabel = opts.confirmLabel || "Confirm";
    var cancelLabel = opts.cancelLabel || "Cancel";
    var danger = !!opts.danger;
    var previouslyFocused = document.activeElement;

    modalIdCounter += 1;
    var titleId = "ui-modal-title-" + modalIdCounter;
    var bodyId = "ui-modal-body-" + modalIdCounter;

    return new Promise(function (resolve) {
      var overlay = document.createElement("div");
      overlay.className = "modal-overlay";

      var modal = document.createElement("div");
      modal.className = "modal";
      modal.setAttribute("role", "alertdialog");
      modal.setAttribute("aria-modal", "true");
      modal.setAttribute("aria-labelledby", titleId);
      modal.setAttribute("aria-describedby", bodyId);

      var titleEl = document.createElement("div");
      titleEl.className = "modal__title";
      titleEl.id = titleId;
      titleEl.textContent = title;

      var bodyEl = document.createElement("div");
      bodyEl.className = "modal__body";
      bodyEl.id = bodyId;
      bodyEl.textContent = body;

      var actions = document.createElement("div");
      actions.className = "modal__actions";

      var cancelBtn = document.createElement("button");
      cancelBtn.type = "button";
      cancelBtn.className = "btn btn-secondary";
      cancelBtn.textContent = cancelLabel;

      var confirmBtn = document.createElement("button");
      confirmBtn.type = "button";
      confirmBtn.className = danger ? "btn btn-danger" : "btn btn-primary";
      confirmBtn.textContent = confirmLabel;

      actions.appendChild(cancelBtn);
      actions.appendChild(confirmBtn);
      modal.appendChild(titleEl);
      modal.appendChild(bodyEl);
      modal.appendChild(actions);
      overlay.appendChild(modal);
      document.body.appendChild(overlay);
      activeModal = overlay;

      var finish = function (result) {
        closeModal(overlay, resolve, result, previouslyFocused);
      };

      cancelBtn.addEventListener("click", function () {
        finish(false);
      });
      confirmBtn.addEventListener("click", function () {
        finish(true);
      });
      overlay.addEventListener("click", function (event) {
        if (event.target === overlay) {
          finish(false);
        }
      });

      overlay._onKeydown = function (event) {
        if (event.key === "Escape") {
          finish(false);
          return;
        }
        // The modal only ever has two focusable elements (Cancel/Confirm)
        // -- Tab/Shift+Tab simply wrap between them, keeping focus from
        // leaking out to the page underneath.
        if (event.key === "Tab") {
          event.preventDefault();
          if (document.activeElement === confirmBtn) {
            cancelBtn.focus();
          } else {
            confirmBtn.focus();
          }
        }
      };
      document.addEventListener("keydown", overlay._onKeydown);

      confirmBtn.focus();
    });
  }

  function skeletonRows(container, count) {
    if (!container) {
      return;
    }
    container.textContent = "";
    var rows = count || 3;
    for (var i = 0; i < rows; i += 1) {
      var row = document.createElement("div");
      row.className = "skeleton skeleton-row";
      container.appendChild(row);
    }
  }

  // Builds a standalone `.empty-state` element (icon + title + description
  // + optional CTA). Callers wrap it in whatever container shape they need
  // (a bare `<div>`/`<li>`, or a `<td>` inside a single-cell `<tr>` for
  // tables) -- this function only builds the reusable inner content.
  function emptyState(options) {
    var opts = options || {};
    var wrap = document.createElement("div");
    wrap.className = "empty-state";

    if (opts.icon) {
      var icon = document.createElement("div");
      icon.className = "empty-state__icon";
      icon.setAttribute("aria-hidden", "true");
      icon.textContent = opts.icon;
      wrap.appendChild(icon);
    }

    if (opts.title) {
      var title = document.createElement("div");
      title.className = "empty-state__title";
      title.textContent = opts.title;
      wrap.appendChild(title);
    }

    if (opts.description) {
      var description = document.createElement("p");
      description.className = "empty-state__description";
      description.textContent = opts.description;
      wrap.appendChild(description);
    }

    if (opts.actionLabel && opts.actionHref) {
      var action = document.createElement("a");
      action.className = "btn btn-secondary empty-state__action";
      action.href = opts.actionHref;
      action.textContent = opts.actionLabel;
      wrap.appendChild(action);
    } else if (opts.actionLabel && typeof opts.onAction === "function") {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "btn btn-secondary empty-state__action";
      button.textContent = opts.actionLabel;
      button.addEventListener("click", opts.onAction);
      wrap.appendChild(button);
    }

    return wrap;
  }

  // Convenience wrapper for the common "empty state inside a single
  // spanning table cell" shape used by every `.ws-table`/`.table` in the
  // workspace (Customers, Event Center, Users, Invitations, API Keys).
  function emptyStateRow(tbody, colSpan, options) {
    if (!tbody) {
      return;
    }
    tbody.textContent = "";
    var row = document.createElement("tr");
    var cell = document.createElement("td");
    cell.colSpan = colSpan;
    cell.appendChild(emptyState(options));
    row.appendChild(cell);
    tbody.appendChild(row);
  }

  window.UI = {
    toast: toast,
    confirm: confirmModal,
    emptyState: emptyState,
    emptyStateRow: emptyStateRow,
    skeletonRows: skeletonRows,
  };
})();
