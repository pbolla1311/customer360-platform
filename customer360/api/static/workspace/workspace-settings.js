(function () {
  "use strict";

  // ---------------------------------------------------------------------
  // Pure logic (no DOM access below this block) -- exercised directly
  // under Node in tests/api/test_workspace_settings_js.py.
  // ---------------------------------------------------------------------

  var ROLE_OPTIONS = [
    { value: "admin", label: "Admin" },
    { value: "operations", label: "Operations" },
    { value: "customer_success", label: "Customer Success" },
    { value: "executive", label: "Executive" },
    { value: "viewer", label: "Viewer" },
  ];

  function roleOptions() {
    return ROLE_OPTIONS.slice();
  }

  function invitationStatusClass(status) {
    if (status === "accepted") {
      return "ws-status-pill--success";
    }
    if (status === "expired" || status === "revoked") {
      return "ws-status-pill--dlq";
    }
    return "ws-status-pill--failed";
  }

  function apiKeyStatusClass(status) {
    return status === "active" ? "ws-status-pill--success" : "ws-status-pill--dlq";
  }

  var SettingsLogic = {
    roleOptions: roleOptions,
    invitationStatusClass: invitationStatusClass,
    apiKeyStatusClass: apiKeyStatusClass,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = SettingsLogic;
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
    var postJson = window.Workspace.postJson;
    var patchJson = window.Workspace.patchJson;
    var relativeTimeLabel = window.Workspace.relativeTimeLabel;
    var roleLabel = window.WorkspaceLogic ? window.WorkspaceLogic.roleLabel : function (r) {
      return r;
    };

    var currentOrgId = null;
    var currentIsAdmin = false;

    // -- Settings sub-tabs --------------------------------------------------

    var settingsTabs = Array.prototype.slice.call(document.querySelectorAll(".ws-tab[data-settings-tab]"));
    var settingsPanels = Array.prototype.slice.call(
      document.querySelectorAll(".ws-tab-panel[data-settings-panel]")
    );

    function activateSettingsTab(tabName) {
      settingsTabs.forEach(function (tab) {
        var isActive = tab.getAttribute("data-settings-tab") === tabName;
        tab.classList.toggle("is-active", isActive);
        tab.setAttribute("aria-selected", isActive ? "true" : "false");
      });
      settingsPanels.forEach(function (panel) {
        panel.classList.toggle("is-hidden", panel.getAttribute("data-settings-panel") !== tabName);
      });

      if (tabName === "organization") {
        loadOrganization();
      } else if (tabName === "users") {
        loadUsers();
      } else if (tabName === "invitations") {
        loadInvitations();
      } else if (tabName === "api-keys") {
        loadApiKeys();
      }
    }

    settingsTabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        activateSettingsTab(tab.getAttribute("data-settings-tab"));
      });
    });

    // -- General tab: reset + system status ----------------------------------

    var settingsResetBtn = document.getElementById("ws-settings-reset");
    var settingsResetStatus = document.getElementById("ws-settings-reset-status");
    var systemStatusEl = document.getElementById("ws-system-status");
    var systemStatusLoaded = false;

    function runSimulationReset() {
      settingsResetBtn.disabled = true;
      postJson("/demo/api/pipeline/reset")
        .then(function () {
          settingsResetStatus.textContent = "Simulation data reset.";
          settingsResetStatus.className = "ws-edit-status ws-edit-status--ok";
          if (window.UI) {
            window.UI.toast("Simulation data reset.", { type: "success" });
          }
        })
        .catch(function (err) {
          var message = (err && err.message) || "Couldn't reset simulation data.";
          settingsResetStatus.textContent = message;
          settingsResetStatus.className = "ws-edit-status ws-edit-status--error";
          if (window.UI) {
            window.UI.toast(message, { type: "error" });
          }
        })
        .then(function () {
          settingsResetBtn.disabled = false;
        });
    }

    if (settingsResetBtn) {
      settingsResetBtn.addEventListener("click", function () {
        if (!window.UI) {
          runSimulationReset();
          return;
        }
        window.UI.confirm({
          title: "Reset all simulation data?",
          body: "This clears every Control Center event, retry, and DLQ entry shared by everyone currently viewing the demo. This cannot be undone.",
          confirmLabel: "Reset Simulation Data",
          danger: true,
        }).then(function (confirmed) {
          if (confirmed) {
            runSimulationReset();
          }
        });
      });
    }

    function loadSystemStatus() {
      if (systemStatusLoaded || !systemStatusEl) {
        return;
      }
      systemStatusLoaded = true;
      fetchJson("/health")
        .then(function (health) {
          systemStatusEl.textContent = health.status + " (v" + health.version + ")";
        })
        .catch(function () {
          systemStatusEl.textContent = "Unavailable";
        });
    }

    // -- Organization branding -----------------------------------------------

    var orgForm = document.getElementById("settings-org-form");
    var orgNameInput = document.getElementById("settings-org-name");
    var orgLogoInput = document.getElementById("settings-org-logo");
    var orgThemeSelect = document.getElementById("settings-org-theme");
    var orgStatus = document.getElementById("settings-org-status");
    var orgLoaded = false;

    function loadOrganization() {
      if (orgLoaded || !currentOrgId) {
        return;
      }
      orgLoaded = true;
      fetchJson("/demo/api/organizations")
        .then(function (orgs) {
          var org = orgs.filter(function (o) {
            return o.id === currentOrgId;
          })[0];
          if (!org) {
            return;
          }
          orgNameInput.value = org.name;
          orgLogoInput.value = org.logo_url || "";
          orgThemeSelect.value = org.theme;
        })
        .catch(function () {});
    }

    if (orgForm) {
      orgForm.addEventListener("submit", function (event) {
        event.preventDefault();
        if (!currentOrgId) {
          return;
        }
        orgStatus.textContent = "Saving…";
        orgStatus.className = "ws-edit-status";
        patchJson("/demo/api/organizations/" + currentOrgId, {
          name: orgNameInput.value,
          logo_url: orgLogoInput.value || null,
          theme: orgThemeSelect.value,
        })
          .then(function () {
            orgStatus.textContent = "Branding saved.";
            orgStatus.className = "ws-edit-status ws-edit-status--ok";
            if (window.UI) {
              window.UI.toast("Organization branding saved.", { type: "success" });
            }
          })
          .catch(function (err) {
            var message = (err && err.message) || "Couldn't save branding.";
            orgStatus.textContent = message;
            orgStatus.className = "ws-edit-status ws-edit-status--error";
            if (window.UI) {
              window.UI.toast(message, { type: "error" });
            }
          });
      });
    }

    // -- Users ----------------------------------------------------------------

    var usersBody = document.getElementById("settings-users-body");

    function renderUsers(members) {
      if (members.length === 0) {
        if (window.UI) {
          window.UI.emptyStateRow(usersBody, 5, {
            icon: "👥",
            title: "No team members yet",
            description: "Invite a teammate from the Invitations tab to start building this organization.",
            actionLabel: "Go to Invitations",
            onAction: function () {
              activateSettingsTab("invitations");
            },
          });
        } else {
          usersBody.textContent = "";
          var row = document.createElement("tr");
          var cell = document.createElement("td");
          cell.colSpan = 5;
          cell.className = "ws-empty-hint";
          cell.textContent = "No members yet.";
          row.appendChild(cell);
          usersBody.appendChild(row);
        }
        return;
      }
      usersBody.textContent = "";

      var nowMs = Date.now();
      members.forEach(function (member) {
        var tr = document.createElement("tr");

        var nameTd = document.createElement("td");
        nameTd.textContent = member.name + " (" + member.email + ")";
        tr.appendChild(nameTd);

        var roleTd = document.createElement("td");
        var roleSelect = document.createElement("select");
        roleSelect.className = "ws-select";
        SettingsLogic.roleOptions().forEach(function (option) {
          var optionEl = document.createElement("option");
          optionEl.value = option.value;
          optionEl.textContent = option.label;
          optionEl.selected = option.value === member.role;
          roleSelect.appendChild(optionEl);
        });
        roleSelect.addEventListener("change", function () {
          patchJson("/demo/api/memberships/" + member.membership_id, {
            role: roleSelect.value,
          })
            .then(function () {
              if (window.UI) {
                window.UI.toast(member.name + "'s role updated to " + roleLabel(roleSelect.value) + ".", {
                  type: "success",
                });
              }
            })
            .catch(function (err) {
              roleSelect.value = member.role;
              if (window.UI) {
                window.UI.toast((err && err.message) || "Couldn't update role.", { type: "error" });
              }
            });
        });
        roleTd.appendChild(roleSelect);
        tr.appendChild(roleTd);

        var statusTd = document.createElement("td");
        statusTd.textContent = member.status;
        tr.appendChild(statusTd);

        var lastLoginTd = document.createElement("td");
        lastLoginTd.textContent = member.last_login_at
          ? relativeTimeLabel(member.last_login_at, nowMs)
          : "Never";
        tr.appendChild(lastLoginTd);

        var actionsTd = document.createElement("td");
        var removeBtn = document.createElement("button");
        removeBtn.type = "button";
        removeBtn.className = "btn btn-secondary";
        removeBtn.textContent = "Remove";
        removeBtn.addEventListener("click", function () {
          var doRemove = function () {
            fetch("/demo/api/memberships/" + member.membership_id, { method: "DELETE" })
              .then(function () {
                loadUsers(true);
                if (window.UI) {
                  window.UI.toast(member.name + " removed from this organization.", { type: "success" });
                }
              })
              .catch(function () {
                if (window.UI) {
                  window.UI.toast("Couldn't remove this member.", { type: "error" });
                }
              });
          };
          if (!window.UI) {
            doRemove();
            return;
          }
          window.UI.confirm({
            title: "Remove this member?",
            body: member.name + " (" + member.email + ") will lose access to this organization.",
            confirmLabel: "Remove Member",
            danger: true,
          }).then(function (confirmed) {
            if (confirmed) {
              doRemove();
            }
          });
        });
        actionsTd.appendChild(removeBtn);
        tr.appendChild(actionsTd);

        usersBody.appendChild(tr);
      });
    }

    function loadUsers(force) {
      if (!currentOrgId) {
        return;
      }
      fetchJson("/demo/api/organizations/" + currentOrgId + "/members")
        .then(renderUsers)
        .catch(function () {});
    }

    // -- Invitations ------------------------------------------------------

    var inviteForm = document.getElementById("invite-form");
    var inviteEmailInput = document.getElementById("invite-email");
    var inviteRoleSelect = document.getElementById("invite-role");
    var inviteStatus = document.getElementById("invite-status");
    var invitationsBody = document.getElementById("invitations-body");

    function renderInvitations(invitations) {
      if (invitations.length === 0) {
        if (window.UI) {
          window.UI.emptyStateRow(invitationsBody, 6, {
            icon: "✉️",
            title: "No invitations sent yet",
            description: "Use the form above to invite a teammate to this organization.",
          });
        } else {
          invitationsBody.textContent = "";
          var row = document.createElement("tr");
          var cell = document.createElement("td");
          cell.colSpan = 6;
          cell.className = "ws-empty-hint";
          cell.textContent = "No invitations yet.";
          row.appendChild(cell);
          invitationsBody.appendChild(row);
        }
        return;
      }
      invitationsBody.textContent = "";

      var nowMs = Date.now();
      invitations.forEach(function (invitation) {
        var tr = document.createElement("tr");

        [invitation.email, roleLabel(invitation.role)].forEach(function (text) {
          var td = document.createElement("td");
          td.textContent = text;
          tr.appendChild(td);
        });

        var statusTd = document.createElement("td");
        var pill = document.createElement("span");
        pill.className = "ws-status-pill " + SettingsLogic.invitationStatusClass(invitation.status);
        pill.textContent = invitation.status.toUpperCase();
        statusTd.appendChild(pill);
        tr.appendChild(statusTd);

        var invitedByTd = document.createElement("td");
        invitedByTd.textContent = invitation.invited_by || "—";
        tr.appendChild(invitedByTd);

        var sentTd = document.createElement("td");
        sentTd.textContent = relativeTimeLabel(invitation.created_at, nowMs);
        tr.appendChild(sentTd);

        var actionsTd = document.createElement("td");
        if (invitation.status === "pending") {
          var revokeBtn = document.createElement("button");
          revokeBtn.type = "button";
          revokeBtn.className = "btn btn-secondary";
          revokeBtn.textContent = "Revoke";
          revokeBtn.addEventListener("click", function () {
            var doRevoke = function () {
              postJson("/demo/api/invitations/" + invitation.id + "/revoke")
                .then(function () {
                  loadInvitations();
                  if (window.UI) {
                    window.UI.toast("Invitation to " + invitation.email + " revoked.", { type: "success" });
                  }
                })
                .catch(function () {
                  if (window.UI) {
                    window.UI.toast("Couldn't revoke this invitation.", { type: "error" });
                  }
                });
            };
            if (!window.UI) {
              doRevoke();
              return;
            }
            window.UI.confirm({
              title: "Revoke this invitation?",
              body: invitation.email + " will no longer be able to accept this invitation.",
              confirmLabel: "Revoke Invitation",
              danger: true,
            }).then(function (confirmed) {
              if (confirmed) {
                doRevoke();
              }
            });
          });
          actionsTd.appendChild(revokeBtn);
        } else {
          actionsTd.textContent = "—";
        }
        tr.appendChild(actionsTd);

        invitationsBody.appendChild(tr);
      });
    }

    function loadInvitations() {
      if (!currentOrgId) {
        return;
      }
      fetchJson("/demo/api/organizations/" + currentOrgId + "/invitations")
        .then(renderInvitations)
        .catch(function () {});
    }

    if (inviteForm) {
      inviteForm.addEventListener("submit", function (event) {
        event.preventDefault();
        if (!currentOrgId) {
          return;
        }
        inviteStatus.textContent = "Sending invitation…";
        inviteStatus.className = "ws-edit-status";
        postJson("/demo/api/organizations/" + currentOrgId + "/invitations", {
          email: inviteEmailInput.value,
          role: inviteRoleSelect.value,
        })
          .then(function () {
            inviteStatus.textContent = "Invitation sent.";
            inviteStatus.className = "ws-edit-status ws-edit-status--ok";
            if (window.UI) {
              window.UI.toast("Invitation sent to " + inviteEmailInput.value + ".", { type: "success" });
            }
            inviteEmailInput.value = "";
            loadInvitations();
          })
          .catch(function (err) {
            var message = (err && err.message) || "Couldn't send invitation.";
            inviteStatus.textContent = message;
            inviteStatus.className = "ws-edit-status ws-edit-status--error";
            if (window.UI) {
              window.UI.toast(message, { type: "error" });
            }
          });
      });
    }

    // -- API keys -----------------------------------------------------------

    var apiKeyForm = document.getElementById("apikey-form");
    var apiKeyNameInput = document.getElementById("apikey-name");
    var apiKeyStatus = document.getElementById("apikey-status");
    var apiKeyReveal = document.getElementById("apikey-reveal");
    var apiKeysBody = document.getElementById("apikeys-body");

    function renderApiKeys(keys) {
      if (keys.length === 0) {
        if (window.UI) {
          window.UI.emptyStateRow(apiKeysBody, 5, {
            icon: "🔑",
            title: "No API keys yet",
            description: "Generate a key above to authenticate programmatic access to this organization.",
          });
        } else {
          apiKeysBody.textContent = "";
          var row = document.createElement("tr");
          var cell = document.createElement("td");
          cell.colSpan = 5;
          cell.className = "ws-empty-hint";
          cell.textContent = "No API keys yet.";
          row.appendChild(cell);
          apiKeysBody.appendChild(row);
        }
        return;
      }
      apiKeysBody.textContent = "";

      var nowMs = Date.now();
      keys.forEach(function (key) {
        var tr = document.createElement("tr");

        var nameTd = document.createElement("td");
        nameTd.textContent = key.name;
        tr.appendChild(nameTd);

        var prefixTd = document.createElement("td");
        prefixTd.textContent = key.key_prefix;
        tr.appendChild(prefixTd);

        var statusTd = document.createElement("td");
        var pill = document.createElement("span");
        pill.className = "ws-status-pill " + SettingsLogic.apiKeyStatusClass(key.status);
        pill.textContent = key.status.toUpperCase();
        statusTd.appendChild(pill);
        tr.appendChild(statusTd);

        var lastUsedTd = document.createElement("td");
        lastUsedTd.textContent = key.last_used_at ? relativeTimeLabel(key.last_used_at, nowMs) : "Never";
        tr.appendChild(lastUsedTd);

        var actionsTd = document.createElement("td");
        if (key.status === "active") {
          var rotateBtn = document.createElement("button");
          rotateBtn.type = "button";
          rotateBtn.className = "btn btn-secondary";
          rotateBtn.textContent = "Rotate";
          rotateBtn.addEventListener("click", function () {
            postJson("/demo/api/api-keys/" + key.id + "/rotate")
              .then(function (result) {
                revealKey(result.full_key);
                loadApiKeys();
                if (window.UI) {
                  window.UI.toast("API key rotated. Copy the new key now.", { type: "success" });
                }
              })
              .catch(function () {
                if (window.UI) {
                  window.UI.toast("Couldn't rotate this key.", { type: "error" });
                }
              });
          });
          var revokeBtn = document.createElement("button");
          revokeBtn.type = "button";
          revokeBtn.className = "btn btn-secondary";
          revokeBtn.textContent = "Revoke";
          revokeBtn.addEventListener("click", function () {
            var doRevoke = function () {
              postJson("/demo/api/api-keys/" + key.id + "/revoke")
                .then(function () {
                  loadApiKeys();
                  if (window.UI) {
                    window.UI.toast("API key \"" + key.name + "\" revoked.", { type: "success" });
                  }
                })
                .catch(function () {
                  if (window.UI) {
                    window.UI.toast("Couldn't revoke this key.", { type: "error" });
                  }
                });
            };
            if (!window.UI) {
              doRevoke();
              return;
            }
            window.UI.confirm({
              title: "Revoke this API key?",
              body: "\"" + key.name + "\" (" + key.key_prefix + ") will stop working immediately.",
              confirmLabel: "Revoke API Key",
              danger: true,
            }).then(function (confirmed) {
              if (confirmed) {
                doRevoke();
              }
            });
          });
          actionsTd.appendChild(rotateBtn);
          actionsTd.appendChild(document.createTextNode(" "));
          actionsTd.appendChild(revokeBtn);
        } else {
          actionsTd.textContent = "—";
        }
        tr.appendChild(actionsTd);

        apiKeysBody.appendChild(tr);
      });
    }

    function loadApiKeys() {
      if (!currentOrgId) {
        return;
      }
      fetchJson("/demo/api/organizations/" + currentOrgId + "/api-keys")
        .then(renderApiKeys)
        .catch(function () {});
    }

    function revealKey(fullKey) {
      apiKeyReveal.textContent =
        "New key (copy it now -- it won't be shown again): " + fullKey;
      apiKeyReveal.classList.remove("is-hidden");
    }

    if (apiKeyForm) {
      apiKeyForm.addEventListener("submit", function (event) {
        event.preventDefault();
        if (!currentOrgId) {
          return;
        }
        apiKeyStatus.textContent = "Generating…";
        apiKeyStatus.className = "ws-edit-status";
        postJson("/demo/api/organizations/" + currentOrgId + "/api-keys", {
          name: apiKeyNameInput.value,
        })
          .then(function (result) {
            apiKeyStatus.textContent = "Key generated.";
            apiKeyStatus.className = "ws-edit-status ws-edit-status--ok";
            if (window.UI) {
              window.UI.toast("API key generated. Copy it now.", { type: "success" });
            }
            apiKeyNameInput.value = "";
            revealKey(result.full_key);
            loadApiKeys();
          })
          .catch(function (err) {
            var message = (err && err.message) || "Couldn't generate key.";
            apiKeyStatus.textContent = message;
            apiKeyStatus.className = "ws-edit-status ws-edit-status--error";
            if (window.UI) {
              window.UI.toast(message, { type: "error" });
            }
          });
      });
    }

    // -- View registration --------------------------------------------------

    window.Workspace.registerView("settings", {
      activate: function () {
        loadSystemStatus();
        fetchJson("/demo/api/auth/session")
          .then(function (session) {
            if (session.organization) {
              currentOrgId = session.organization.id;
            }
            currentIsAdmin = session.role === "admin";
          })
          .catch(function () {});
      },
      deactivate: function () {},
    });
  });
})();
