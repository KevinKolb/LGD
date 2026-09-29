"use strict";
/* The one footer every page in this app shares. Included as
 * <script src=".../shared/footer.js"></script> just before </body>, so the
 * links only ever have to change in one place.
 *
 * Injected rather than copied into each page's HTML for the same reason
 * manager/account.js injects the account bar: there is no template
 * engine here, and six hand-kept copies of the same markup drift. */

(function () {
  // Resident first, then applicant; admin always last. Sign in is last of
  // all and separated from the role links - it is not a fifth area of the
  // site, it is how you get into the other four.
  const LINKS = [
    { path: "resident/", text: "Resident" },
    { path: "applicant/", text: "Applicant" },
    { path: "manager/", text: "Manager" },
    { path: "admin/", text: "Admin" },
    { path: "login/", text: "Sign in" },
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

  // A floating Home button, bottom right, on every page but home itself.
  // A page with its own floating buttons (the legal pages' Back) puts them
  // in a .site-float group, and Home joins it on the left; otherwise the
  // group is made here. The printable documents do not load this script -
  // they are self-contained files - and carry their own Home the same way.
  const here = window.location.href.split(/[?#]/)[0].replace(/index\.html$/, "");
  if (here === root) return;
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
  let group = document.querySelector(".site-float");
  if (!group) {
    group = document.createElement("div");
    group.className = "site-float";
    document.body.append(group);
  }
  const home = document.createElement("a");
  home.href = root;
  home.className = "home-button";
  home.textContent = "Home";
  group.prepend(home);
})();
