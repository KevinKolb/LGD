"use strict";
/* Home, on the main pages (the user, 2026-10-02: "really just need a back
 * button in upper right. don't need the footer", then the same day:
 * "rename back to home and put it in a better place"). Loaded just before
 * </body> on the applicant, resident, manager and admin pages and the
 * sign-in page - not the home page itself. It replaced shared/footer.js,
 * the row of links at the bottom of every page.
 *
 * The header gets a top row: Home on the left, the account control
 * (Login/Logout, from shared/account.js, loaded first) on the right, both
 * one size, with the page's title beneath them - so on a phone neither
 * squeezes the title. A page with no header bar (sign-in) floats Home in
 * the top-left corner instead. */

(function () {
  // The site root, from this script's own URL: GitHub Pages serves the
  // site under /LGD/, the FastAPI app at the domain root.
  const src = document.currentScript ? document.currentScript.src : window.location.href;
  const root = src.replace(/shared\/home\.js(?:\?.*)?$/, "");

  const style = document.createElement("style");
  style.textContent = `
    header.has-home { position: relative; padding-top: 60px; }
    header.has-home > #home-button,
    header.has-home > #account-bar { position: absolute; top: 16px; }
    header.has-home > #account-bar { right: 16px; }
    #home-button, header.has-home #account-toggle {
      box-sizing: border-box; height: 32px; min-width: 84px;
      display: inline-flex; align-items: center; justify-content: center;
      padding: 0 12px; font: inherit; font-size: 13px; line-height: 1;
      border: 1px solid rgba(255, 255, 255, .6); border-radius: 6px;
      background: transparent; color: inherit; text-decoration: none;
      cursor: pointer; text-transform: uppercase; letter-spacing: .03em;
    }
    #home-button:hover { background: rgba(255, 255, 255, .15); }
    /* A page with no header bar (sign-in): Home floats in the corner. */
    #home-button.floating {
      position: fixed; top: 16px; left: 16px; z-index: 20;
      border-color: var(--accent, #1f5d4c); color: var(--accent, #1f5d4c); background: #fff;
    }
    @media print { #home-button, #account-bar { display: none; } }`;
  document.head.append(style);

  const home = document.createElement("a");
  home.id = "home-button";
  home.href = root;
  home.textContent = "Home";

  const header = document.querySelector("header:not(.site-title)");
  if (!header) {
    home.classList.add("floating");
    document.body.append(home);
    return;
  }
  header.classList.add("has-home");
  // Home lines up with the title's left edge.
  home.style.left = (parseFloat(getComputedStyle(header).paddingLeft) || 24) + "px";
  header.prepend(home);
  const accountBar = document.getElementById("account-bar");
  if (accountBar && accountBar.parentNode !== header) header.append(accountBar);
})();
