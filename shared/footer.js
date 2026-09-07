"use strict";
/* The one footer every page in this app shares. Included as
 * <script src=".../shared/footer.js"></script> just before </body>, so the
 * links only ever have to change in one place.
 *
 * Injected rather than copied into each page's HTML for the same reason
 * manager/account.js injects the account bar: there is no template
 * engine here, and six hand-kept copies of the same markup drift. */

(function () {
  // Tenant first, then applicant; admin always last.
  const LINKS = [
    { path: "tenant/", text: "Tenant" },
    { path: "applicant/", text: "Applicant" },
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

  const footer = document.createElement("footer");
  for (const link of LINKS) {
    const anchor = document.createElement("a");
    anchor.href = root + link.path;
    anchor.textContent = link.text;
    footer.append(anchor);
  }
  document.body.append(footer);
})();
