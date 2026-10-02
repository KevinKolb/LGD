"use strict";
/* Managers and admins only, for a page with nothing else guarding it - the
 * legal checklist and the legal research log (the user, 2026-10-02: "fix
 * all access problems"; until then anyone could open them). Load it in the
 * <head>, after shared/auth.js:
 *
 *     <script src="../shared/auth.js"></script>
 *     <script src="../shared/staff-gate.js"></script>
 *
 * The page stays hidden until the login is checked. Signed out, it goes to
 * the sign-in page and comes back; signed in without the role, it says so,
 * with Home. Served by the FastAPI app, HTTP Basic has already let only a
 * manager or admin in, and /api/config answers.
 *
 * The page's text is in this public repository anyway; what this fixes is
 * the site handing it to anyone who follows a link. */
(function () {
  const page = document.documentElement;
  page.style.visibility = "hidden";
  const show = () => { page.style.visibility = ""; };

  function refuse(text) {
    const home = (window.LGD && window.LGD.auth && window.LGD.auth.root) || "../";
    document.body.innerHTML = "";
    const box = document.createElement("div");
    box.setAttribute("style", "max-width:360px;margin:15vh auto 0;padding:28px 24px;text-align:center;" +
      "font:15px/1.5 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;" +
      "background:#fff;border:1px solid #d9d9d9;border-radius:8px;color:#1a1a1a;");
    const message = document.createElement("p");
    message.setAttribute("style", "margin:0 0 18px;");
    message.textContent = text;
    const link = document.createElement("a");
    link.href = home;
    link.textContent = "Home";
    link.setAttribute("style", "display:inline-block;padding:9px 22px;border-radius:999px;" +
      "border:1px solid #1f5d4c;color:#1f5d4c;text-decoration:none;font-weight:600;");
    box.append(message, link);
    document.body.append(box);
    show();
  }

  async function check() {
    try {
      const response = await fetch("/api/config");
      if (response.ok) return show();
    } catch (error) {
      /* No FastAPI app here - the normal case on GitHub Pages. */
    }
    const auth = window.LGD && window.LGD.auth;
    if (!auth || !auth.configured) return refuse("This page is for managers, and the login service is not connected.");
    const result = await auth.requireRole(["manager", "admin"]);
    if (result.ok) return show();
    if (result.reason === "signed-out") return;   // already on the way to sign in
    if (result.reason === "unconfirmed") return refuse("Your account is not confirmed yet. Click the link in the email we sent, then come back.");
    refuse("This page is for managers.");
  }

  const run = () => check().catch(() => refuse("Your access could not be checked. Try again."));
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", run);
  else run();
})();
