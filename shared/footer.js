"use strict";
/* The one footer every page in this app shares. Included as
 * <script src=".../shared/footer.js"></script> just before </body>, so the
 * links only ever have to change in one place.
 *
 * Injected rather than copied into each page's HTML for the same reason
 * manager/account.js injects the account bar: there is no template
 * engine here, and six hand-kept copies of the same markup drift. */

(function () {
  // Applicant first, then resident; admin always last. No "Sign in" link
  // (removed 2026-09-29, the user): a page that needs a login - manager,
  // admin - sends a signed-out visitor to the sign-in page itself, and
  // back to that page afterwards (shared/auth.js, requireRole).
  const LINKS = [
    { path: "applicant/", text: "Applicant" },
    { path: "resident/", text: "Resident" },
    { path: "manager/", text: "Manager" },
    { path: "admin/", text: "Admin" },
  ];

  // Where the site root is, worked out from this script's own URL rather
  // than hardcoded: on Render the app is served from the domain root, but
  // GitHub Pages serves this repo under a /LGD/ prefix, and absolute
  // "/manager/" links would miss it entirely.
  const src = document.currentScript
    ? document.currentScript.src
    : window.location.href;
  const root = src.replace(/shared\/footer\.js(?:\?.*)?$/, "");

  const here = window.location.href.split(/[?#]/)[0].replace(/index\.html$/, "");
  const onHome = here === root;

  // Home is an ordinary footer link, first, on every page but home itself
  // (the user, 2026-09-29: "like everything else").
  const footer = document.createElement("footer");
  const links = onHome ? LINKS : [{ path: "", text: "Home" }].concat(LINKS);
  for (const link of links) {
    const anchor = document.createElement("a");
    anchor.href = root + link.path;
    anchor.textContent = link.text;
    footer.append(anchor);
  }
  document.body.append(footer);

  // The document-style pages - the legal research log and checklist - also
  // float Home beside their own Back button: they put Back in a .site-float
  // group before this script, and Home joins it on the left. Ordinary pages
  // have no group and float nothing. (The printable documents do not load
  // this script; they float Back and Print only.)
  const group = document.querySelector(".site-float");
  if (onHome || !group) return;
  const style = document.createElement("style");
  style.textContent = `
    .site-float {
      position: fixed; right: 16px; bottom: 16px; z-index: 20;
      display: flex; gap: 10px;
    }
    .site-float a {
      padding: 10px 20px;
      border: 1px solid #1f5d4c;
      border-radius: 999px;
      background: #fff;
      color: #1f5d4c;
      font: inherit;
      text-decoration: none;
      box-shadow: 0 3px 12px rgba(0, 0, 0, .25);
    }
    @media (max-width: 420px) {
      .site-float { right: 10px; bottom: 10px; gap: 8px; }
      .site-float a { padding: 7px 14px; }
    }
    @media print { .site-float { display: none; } }`;
  document.head.append(style);
  const home = document.createElement("a");
  home.href = root;
  home.className = "home-button";
  home.textContent = "Home";
  group.prepend(home);
})();
