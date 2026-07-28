(function () {
  "use strict";

  // ---------------------------------------------------------------------
  // Pure logic (no DOM access below this block) -- exercised directly
  // under Node in tests/api/test_login_js.py.
  // ---------------------------------------------------------------------

  // Deterministic initials from a full name -- "Sarah Johnson" -> "SJ".
  function initialsFor(name) {
    var parts = String(name || "")
      .trim()
      .split(/\s+/)
      .filter(function (part) {
        return part.length > 0;
      });
    if (parts.length === 0) {
      return "?";
    }
    if (parts.length === 1) {
      return parts[0].slice(0, 2).toUpperCase();
    }
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }

  // A fixed 5-class palette, picked deterministically -- CSP's strict
  // style-src (no unsafe-inline) blocks JS-set element.style mutations
  // just as it blocks inline style="" attributes, so avatar color can't
  // be assigned from the arbitrary avatar_color string directly; this
  // hashes an identity string (the user's email) onto one of a handful
  // of predefined CSS classes instead. Same deterministic-hash technique
  // demo.js already uses for its illustrative timeline.
  var AVATAR_PALETTE = ["blue", "cyan", "violet", "green", "amber"];

  function avatarClassFor(seed) {
    var text = String(seed || "");
    var hash = 0;
    for (var i = 0; i < text.length; i += 1) {
      hash = (hash * 31 + text.charCodeAt(i)) >>> 0;
    }
    return "login-user-avatar--" + AVATAR_PALETTE[hash % AVATAR_PALETTE.length];
  }

  var LoginLogic = {
    initialsFor: initialsFor,
    avatarClassFor: avatarClassFor,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = LoginLogic;
  }

  // ---------------------------------------------------------------------
  // DOM wiring -- skipped entirely outside a browser (e.g. under Node).
  // ---------------------------------------------------------------------

  if (typeof document === "undefined") {
    return;
  }

  document.addEventListener("DOMContentLoaded", function () {
    function fetchJson(url) {
      return fetch(url, { cache: "no-store" }).then(function (response) {
        if (!response.ok) {
          throw new Error("Request to " + url + " failed with " + response.status);
        }
        return response.json();
      });
    }

    function postJson(url, body) {
      return fetch(url, {
        method: "POST",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }).then(function (response) {
        return response
          .json()
          .catch(function () {
            return null;
          })
          .then(function (data) {
            if (!response.ok) {
              throw new Error((data && data.detail) || "Request failed with " + response.status);
            }
            return data;
          });
      });
    }

    var tabs = Array.prototype.slice.call(document.querySelectorAll(".login-tab"));
    var panels = Array.prototype.slice.call(document.querySelectorAll(".login-panel"));

    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        var target = tab.getAttribute("data-panel");
        tabs.forEach(function (t) {
          var isActive = t === tab;
          t.classList.toggle("is-active", isActive);
          t.setAttribute("aria-selected", isActive ? "true" : "false");
        });
        panels.forEach(function (panel) {
          panel.classList.toggle("is-hidden", panel.getAttribute("data-panel") !== target);
        });
      });
    });

    var userList = document.getElementById("login-user-list");
    var signinStatus = document.getElementById("signin-status");
    var workspacePicker = document.getElementById("workspace-picker");
    var workspacePickerList = document.getElementById("workspace-picker-list");

    function renderUserItem(container, user, onClick) {
      var item = document.createElement("button");
      item.type = "button";
      item.className = "login-user-item";

      var avatar = document.createElement("span");
      avatar.className = "login-user-avatar " + LoginLogic.avatarClassFor(user.email || user.name);
      avatar.textContent = LoginLogic.initialsFor(user.name);

      var body = document.createElement("span");
      body.className = "login-user-body";
      var name = document.createElement("span");
      name.className = "login-user-name";
      name.textContent = user.name;
      var meta = document.createElement("span");
      meta.className = "login-user-meta";
      meta.textContent = user.email;
      body.appendChild(name);
      body.appendChild(meta);

      item.appendChild(avatar);
      item.appendChild(body);
      item.addEventListener("click", onClick);
      container.appendChild(item);
    }

    function renderWorkspacePicker(userId, organizations) {
      workspacePickerList.textContent = "";
      organizations.forEach(function (org) {
        renderUserItem(
          workspacePickerList,
          { name: org.name, email: "/" + org.slug, avatar_color: "#a78bfa" },
          function () {
            switchWorkspace(org.id);
          }
        );
      });
      workspacePicker.classList.remove("is-hidden");
      userList.classList.add("is-hidden");
    }

    function switchWorkspace(organizationId) {
      signinStatus.textContent = "Signing in…";
      signinStatus.className = "login-status";
      postJson("/demo/api/auth/switch-workspace", { organization_id: organizationId })
        .then(function () {
          window.location.href = "/workspace";
        })
        .catch(function (err) {
          signinStatus.textContent = err.message || "Couldn't switch workspace.";
          signinStatus.className = "login-status login-status--error";
        });
    }

    function selectUser(userId) {
      signinStatus.textContent = "Signing in…";
      signinStatus.className = "login-status";
      postJson("/demo/api/auth/login", { user_id: userId })
        .then(function (session) {
          if (session.organization) {
            window.location.href = "/workspace";
            return;
          }
          renderWorkspacePicker(userId, session.available_organizations || []);
          signinStatus.textContent = "";
        })
        .catch(function (err) {
          signinStatus.textContent = err.message || "Couldn't sign in.";
          signinStatus.className = "login-status login-status--error";
        });
    }

    function loadUsers() {
      fetchJson("/demo/api/auth/users")
        .then(function (users) {
          userList.textContent = "";
          if (users.length === 0) {
            var empty = document.createElement("li");
            empty.className = "ws-empty-hint";
            empty.textContent = "No demo users yet -- create an organization instead.";
            userList.appendChild(empty);
            return;
          }
          users.forEach(function (user) {
            renderUserItem(userList, user, function () {
              selectUser(user.id);
            });
          });
        })
        .catch(function () {
          userList.textContent = "";
          var errorItem = document.createElement("li");
          errorItem.className = "ws-empty-hint";
          errorItem.textContent = "Couldn't load demo users.";
          userList.appendChild(errorItem);
        });
    }

    var signupForm = document.getElementById("signup-form");
    var signupStatus = document.getElementById("signup-status");

    if (signupForm) {
      signupForm.addEventListener("submit", function (event) {
        event.preventDefault();
        signupStatus.textContent = "Creating organization…";
        signupStatus.className = "login-status";

        postJson("/demo/api/organizations", {
          name: document.getElementById("signup-org-name").value,
          admin_name: document.getElementById("signup-admin-name").value,
          admin_email: document.getElementById("signup-admin-email").value,
        })
          .then(function () {
            window.location.href = "/workspace";
          })
          .catch(function (err) {
            signupStatus.textContent = err.message || "Couldn't create the organization.";
            signupStatus.className = "login-status login-status--error";
          });
      });
    }

    // If already fully signed in, skip the picker entirely.
    fetchJson("/demo/api/auth/session")
      .then(function (session) {
        if (session.user && session.organization) {
          window.location.href = "/workspace";
          return;
        }
        loadUsers();
      })
      .catch(loadUsers);
  });
})();
