"use strict";
/* The account control in the page header: who is signed in, log out, and
 * change your password. Include it after shared/auth.js on any page that
 * has a <header>:
 *
 *     <script src="../shared/auth.js"></script>
 *     <script src="../shared/account.js"></script>
 *
 * Every page shares this one file so the login state looks and behaves the
 * same everywhere, the same reason shared/footer.js exists.
 *
 * This replaced manager/account.js, which drove HTTP Basic auth against the
 * FastAPI app - a scheme with no real logout at all (the browser cached the
 * credentials and the best anyone could do was deliberately fail a request
 * with garbage). Signing out is now an actual thing that happens: the
 * session token is revoked at Supabase and erased from this device.
 */

(function () {
  const auth = window.LGD && window.LGD.auth;
  if (!auth) return;

  const STYLE = `
    #account-bar { display: flex; align-items: center; gap: 10px; }
    #account-widget { position: relative; }
    #account-toggle {
      font: inherit; font-size: 13px; padding: 6px 12px; border-radius: 6px;
      border: 1px solid rgba(255,255,255,.6); background: transparent;
      color: inherit; cursor: pointer;
      text-transform: uppercase; letter-spacing: .03em;
    }
    #account-popup {
      position: absolute; top: 100%; right: 0; margin-top: 8px;
      width: 300px; max-width: calc(100vw - 32px);
      background: var(--panel, #fff); color: var(--ink, #1c1c1a);
      border: 1px solid var(--line, #dcdad4);
      border-radius: 8px; box-shadow: 0 8px 24px rgba(0,0,0,.18);
      padding: 16px; z-index: 1000; font-size: 13px; line-height: 1.5;
    }
    #account-popup h3 {
      margin: 0 0 10px; font-size: 12px; text-transform: uppercase;
      letter-spacing: .05em; color: var(--muted, #6b6a66);
    }
    #account-popup .who { margin: 0 0 4px; font-size: 14px; font-weight: 600; }
    #account-popup .who-detail { margin: 0 0 14px; color: var(--muted, #6b6a66); }
    #account-popup section {
      margin-bottom: 14px; padding-bottom: 14px; border-bottom: 1px solid #ecebe7;
    }
    #account-popup section:last-child {
      border-bottom: none; margin-bottom: 0; padding-bottom: 0;
    }
    #account-popup input {
      width: 100%; padding: 6px 8px; margin-bottom: 8px;
      border: 1px solid var(--line, #dcdad4);
      border-radius: 5px; font: inherit; box-sizing: border-box;
    }
    #account-popup button {
      font: inherit; padding: 7px 12px; border-radius: 5px;
      border: 1px solid var(--accent, #1f5d4c);
      background: var(--accent, #1f5d4c); color: var(--accent-ink, #fff);
      cursor: pointer; font-size: 13px;
      text-transform: uppercase; letter-spacing: .03em;
    }
    #account-popup button.secondary {
      background: transparent; color: var(--accent, #1f5d4c);
    }
    #account-popup .msg { font-size: 12px; margin: 6px 0 0; }
    #account-popup .msg.error { color: var(--danger, #9b2c2c); }
    #account-popup .msg.ok { color: var(--accent, #1f5d4c); }
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
    container.querySelectorAll(".msg").forEach((node) => node.remove());
    if (!text) return;
    container.append(el("p", { class: `msg ${isError ? "error" : "ok"}`, text }));
  }

  function buildPopup(profile, email) {
    const popup = el("div", { id: "account-popup" });
    popup.append(
      el("p", { class: "who", text: profile ? profile.display_name : "Signed in" }),
      el("p", { class: "who-detail", text: profile ? `${email} — ${profile.role}` : email })
    );

    const passwordSection = el("section", {});
    passwordSection.append(el("h3", { text: "Change password" }));
    const currentInput = el("input", {
      type: "password", placeholder: "Current password", autocomplete: "current-password",
    });
    const newInput = el("input", {
      type: "password", placeholder: "New password (12+ characters)", autocomplete: "new-password",
    });
    const confirmInput = el("input", {
      type: "password", placeholder: "Confirm new password", autocomplete: "new-password",
    });
    const passwordButton = el("button", { type: "button", text: "Update password" });
    passwordSection.append(currentInput, newInput, confirmInput, passwordButton);
    popup.append(passwordSection);

    passwordButton.addEventListener("click", async () => {
      showMessage(passwordSection, "", false);
      if (newInput.value !== confirmInput.value) {
        showMessage(passwordSection, "New passwords do not match.", true);
        return;
      }
      if (newInput.value.length < 12) {
        showMessage(passwordSection, "Use at least 12 characters.", true);
        return;
      }
      passwordButton.disabled = true;
      try {
        // Prove the current password before changing it. Supabase does not
        // require this - the session alone is enough - but an unattended,
        // still-signed-in browser should not be one click from a new
        // password, and it catches a stale autofill too.
        await auth.signIn(email, currentInput.value);
        await auth.updatePassword(newInput.value);
        showMessage(passwordSection, "Password updated.", false);
        currentInput.value = newInput.value = confirmInput.value = "";
      } catch (error) {
        showMessage(passwordSection, error.message, true);
      } finally {
        passwordButton.disabled = false;
      }
    });

    const outSection = el("section", {});
    const outButton = el("button", { type: "button", class: "secondary", text: "Log out" });
    outSection.append(outButton);
    popup.append(outSection);
    outButton.addEventListener("click", async () => {
      outButton.disabled = true;
      await auth.signOut();
      window.location.reload();
    });

    return popup;
  }

  async function boot() {
    const style = document.createElement("style");
    style.textContent = STYLE;
    document.head.append(style);

    const widget = el("div", { id: "account-widget" });
    const toggle = el("button", { type: "button", id: "account-toggle", text: "Account" });
    widget.append(toggle);
    const bar = el("div", { id: "account-bar" }, widget);

    const header = document.querySelector("header");
    if (header) header.append(bar);
    else document.body.prepend(bar);

    const session = await auth.session();
    const profile = session ? await auth.profile() : null;
    const email = session && session.user ? session.user.email : (profile ? profile.email : "");
    toggle.textContent = session ? "Logout" : "Login";

    toggle.addEventListener("click", () => {
      if (!session) {
        auth.goToLogin();
        return;
      }
      const existing = document.getElementById("account-popup");
      if (existing) {
        existing.remove();
        return;
      }
      widget.append(buildPopup(profile, email));
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
