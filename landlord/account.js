"use strict";
/* Shared account bar: a directly-visible sandbox/live toggle (admin only)
 * plus an account popup (who's logged in, log out, change password).
 * Included on every /landlord/ page via
 * <script src="/landlord/account.js"></script> so all of them stay in
 * sync automatically rather than copy-pasting this into each page. */

(function () {
  const STYLE = `
    #account-bar { display: flex; align-items: center; gap: 10px; }
    #mode-toggle {
      display: flex; border: 1px solid rgba(255,255,255,.6); border-radius: 6px;
      overflow: hidden;
    }
    #mode-toggle button {
      font: inherit; font-size: 13px; padding: 6px 12px; border: none;
      background: transparent; color: inherit; cursor: pointer; opacity: .75;
    }
    #mode-toggle button.active { background: rgba(255,255,255,.28); opacity: 1; font-weight: 600; }
    #account-widget { position: relative; }
    #account-toggle {
      font: inherit; font-size: 13px; padding: 6px 12px; border-radius: 6px;
      border: 1px solid rgba(255,255,255,.6); background: transparent;
      color: inherit; cursor: pointer;
    }
    #account-popup {
      position: absolute; top: 100%; right: 0; margin-top: 8px;
      width: 300px; max-width: calc(100vw - 32px);
      background: #fff; color: #1c1c1a; border: 1px solid #dcdad4;
      border-radius: 8px; box-shadow: 0 8px 24px rgba(0,0,0,.18);
      padding: 16px; z-index: 1000; font-size: 13px; line-height: 1.5;
    }
    #account-popup h3 {
      margin: 0 0 10px; font-size: 12px; text-transform: uppercase;
      letter-spacing: .05em; color: #6b6a66;
    }
    #account-popup .who { margin: 0 0 14px; font-size: 14px; }
    #account-popup section { margin-bottom: 14px; padding-bottom: 14px; border-bottom: 1px solid #ecebe7; }
    #account-popup section:last-child { border-bottom: none; margin-bottom: 0; padding-bottom: 0; }
    #account-popup label { display: block; font-weight: 600; margin-bottom: 3px; }
    #account-popup input, #account-popup select {
      width: 100%; padding: 6px 8px; margin-bottom: 8px; border: 1px solid #dcdad4;
      border-radius: 5px; font: inherit; box-sizing: border-box;
    }
    #account-popup button {
      font: inherit; padding: 7px 12px; border-radius: 5px; border: 1px solid #1f5d4c;
      background: #1f5d4c; color: #fff; cursor: pointer; font-size: 13px;
    }
    #account-popup button.secondary { background: transparent; color: #1f5d4c; }
    #account-popup .note { color: #6b6a66; font-size: 11px; margin: 4px 0 0; }
    #account-popup .msg { font-size: 12px; margin: 6px 0 0; }
    #account-popup .msg.error { color: #9b2c2c; }
    #account-popup .msg.ok { color: #1f5d4c; }
  `;

  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
      if (key === "class") node.className = value;
      else if (key === "text") node.textContent = value;
      else if (value !== null && value !== undefined) node.setAttribute(key, value);
    }
    for (const child of children) node.append(child);
    return node;
  }

  function showMessage(container, text, isError) {
    container.querySelectorAll(".msg").forEach((n) => n.remove());
    if (!text) return;
    container.append(el("p", { class: `msg ${isError ? "error" : "ok"}` , text }));
  }

  async function logout() {
    // HTTP Basic Auth has no real logout - the browser caches credentials
    // per origin once entered. This is the standard best-effort trick:
    // deliberately fail auth with garbage credentials so the browser
    // forgets the good ones. It does not work in every browser; closing
    // the tab/window is the one guaranteed way to end the session.
    try {
      await fetch("/api/config", {
        headers: { Authorization: "Basic " + btoa("logged-out:" + Math.random()) },
        cache: "no-store",
      });
    } catch (error) {
      /* ignore - the point was the attempt, not the response */
    }
    window.location.reload();
  }

  function buildPopup(config) {
    const popup = el("div", { id: "account-popup" });
    popup.append(
      el("p", { class: "who", text: `${config.user.display_name} (${config.user.role})` })
    );

    const passwordSection = el("section", {});
    passwordSection.append(el("h3", { text: "Change password" }));
    const currentInput = el("input", { type: "password", placeholder: "Current password", autocomplete: "current-password" });
    const newInput = el("input", { type: "password", placeholder: "New password (12+ characters)", autocomplete: "new-password" });
    const confirmInput = el("input", { type: "password", placeholder: "Confirm new password", autocomplete: "new-password" });
    const passwordButton = el("button", { type: "button", text: "Update password" });
    passwordSection.append(currentInput, newInput, confirmInput, passwordButton);
    popup.append(passwordSection);

    passwordButton.addEventListener("click", async () => {
      showMessage(passwordSection, "", false);
      if (newInput.value !== confirmInput.value) {
        showMessage(passwordSection, "New passwords do not match.", true);
        return;
      }
      passwordButton.disabled = true;
      try {
        const response = await fetch("/api/account/password", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            current_password: currentInput.value,
            new_password: newInput.value,
          }),
        });
        const body = await response.json().catch(() => ({}));
        if (response.ok) {
          showMessage(passwordSection, "Password updated.", false);
          currentInput.value = "";
          newInput.value = "";
          confirmInput.value = "";
        } else {
          showMessage(passwordSection, body.detail || `Failed (HTTP ${response.status}).`, true);
        }
      } catch (error) {
        showMessage(passwordSection, `Could not reach the server: ${error.message}`, true);
      } finally {
        passwordButton.disabled = false;
      }
    });

    const logoutSection = el("section", {});
    const logoutButton = el("button", { type: "button", class: "secondary", text: "Log out" });
    logoutSection.append(
      logoutButton,
      el("p", { class: "note", text: "Best-effort - if it doesn't prompt you again, close this tab." })
    );
    popup.append(logoutSection);
    logoutButton.addEventListener("click", logout);

    return popup;
  }

  function setUpModeToggle(modeToggle, config) {
    const sandboxButton = modeToggle.querySelector('[data-mode="sandbox"]');
    const liveButton = modeToggle.querySelector('[data-mode="production"]');

    function markActive(isSandbox) {
      sandboxButton.classList.toggle("active", isSandbox);
      liveButton.classList.toggle("active", !isSandbox);
    }
    markActive(config.is_sandbox);

    async function setMode(mode) {
      if (mode === "production" && !window.confirm(
        "Switch to production mode? Every lease generated from now on " +
        "spends one of the 60 real documents in the annual allowance."
      )) return;
      try {
        const response = await fetch("/api/admin/mode", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ mode }),
        });
        const body = await response.json().catch(() => ({}));
        if (response.ok) window.location.reload();
        else window.alert(body.detail || `Failed (HTTP ${response.status}).`);
      } catch (error) {
        window.alert(`Could not reach the server: ${error.message}`);
      }
    }
    sandboxButton.addEventListener("click", () => setMode("sandbox"));
    liveButton.addEventListener("click", () => setMode("production"));
    modeToggle.hidden = false;
  }

  async function boot() {
    const style = document.createElement("style");
    style.textContent = STYLE;
    document.head.append(style);

    const bar = el("div", { id: "account-bar" });

    const modeToggle = el("div", { id: "mode-toggle", hidden: "hidden" });
    modeToggle.append(
      el("button", { type: "button", "data-mode": "sandbox", title: "For testing purposes.", text: "Sandbox" }),
      el("button", { type: "button", "data-mode": "production", text: "Live" })
    );

    const widget = el("div", { id: "account-widget" });
    const toggle = el("button", { type: "button", id: "account-toggle", text: "Account" });
    widget.append(toggle);

    bar.append(modeToggle, widget);

    const header = document.querySelector("header");
    if (header) header.append(bar);
    else document.body.prepend(bar);

    let config = null;
    try {
      const response = await fetch("/api/config");
      if (response.ok) config = await response.json();
    } catch (error) {
      /* bar stays present but inert if config can't load */
    }

    if (config && config.user.is_admin) {
      setUpModeToggle(modeToggle, config);
    }

    toggle.addEventListener("click", () => {
      if (!config) return;
      const existing = document.getElementById("account-popup");
      if (existing) {
        existing.remove();
        return;
      }
      widget.append(buildPopup(config));
    });

    document.addEventListener("click", (event) => {
      const popup = document.getElementById("account-popup");
      if (!popup) return;
      if (widget.contains(event.target)) return;
      popup.remove();
    });
  }

  boot();
})();
