"use strict";
/* Back, in the upper right of the page's header (the user, 2026-10-02:
 * "really just need a back button in upper right. don't need the footer").
 * Loaded just before </body> on the applicant, resident, manager and admin
 * pages and the sign-in page - not the home page, which is where Back
 * leads. It replaced shared/footer.js, the row of links at the bottom of
 * every page.
 *
 * Back returns to the page that opened this one when it was this site,
 * else to the home page. On a page with the account control
 * (shared/account.js, loaded first), Back sits beside it, rightmost. */

(function () {
  // The site root, from this script's own URL: GitHub Pages serves the
  // site under /LGD/, the FastAPI app at the domain root.
  const src = document.currentScript ? document.currentScript.src : window.location.href;
  const root = src.replace(/shared\/back\.js(?:\?.*)?$/, "");

  const style = document.createElement("style");
  style.textContent = `
    header.has-back { position: relative; }
    #back-bar {
      position: absolute; top: 16px; right: 16px;
      display: flex; align-items: center; gap: 10px;
    }
    #back-button {
      display: inline-block;
      font: inherit; font-size: 13px; line-height: 1.2;
      padding: 6px 12px; border-radius: 6px;
      border: 1px solid rgba(255, 255, 255, .6); background: transparent;
      color: inherit; text-decoration: none; cursor: pointer;
      text-transform: uppercase; letter-spacing: .03em;
    }
    #back-button:hover { background: rgba(255, 255, 255, .15); }
    /* A page with no header bar (sign-in): Back floats in the corner. */
    #back-bar.floating { position: fixed; z-index: 20; }
    #back-bar.floating #back-button {
      border-color: var(--accent, #1f5d4c); color: var(--accent, #1f5d4c); background: #fff;
    }
    @media print { #back-bar { display: none; } }`;
  document.head.append(style);

  const back = document.createElement("a");
  back.id = "back-button";
  back.href = root;
  back.textContent = "Back";
  back.addEventListener("click", (event) => {
    let cameFromHere = false;
    try {
      cameFromHere = new URL(document.referrer).origin === window.location.origin;
    } catch (error) {
      /* No referrer: opened directly, so Back goes home. */
    }
    if (cameFromHere && window.history.length > 1) {
      event.preventDefault();
      window.history.back();
    }
  });

  // Upper right of the header bar, with the account control (if the page
  // has one) to its left. The header keeps room for them on the right, so
  // its title wraps beside them rather than under them.
  const bar = document.createElement("div");
  bar.id = "back-bar";
  const header = document.querySelector("header:not(.site-title)");
  const accountBar = document.getElementById("account-bar");
  if (accountBar) bar.append(accountBar);
  bar.append(back);
  if (!header) {
    bar.classList.add("floating");
    document.body.append(bar);
    return;
  }
  header.classList.add("has-back");
  header.append(bar);
  const room = () => {
    header.style.paddingRight = "";
    const base = parseFloat(getComputedStyle(header).paddingRight) || 0;
    header.style.paddingRight = Math.max(base, bar.offsetWidth + 28) + "px";
  };
  room();
  window.addEventListener("resize", room);
  // The account control renames itself (Login / Logout) once it knows.
  new MutationObserver(room).observe(bar, { childList: true, subtree: true, characterData: true });
  // The manager page keeps its header hidden until the login is checked.
  new MutationObserver(room).observe(header, { attributes: true, attributeFilter: ["hidden"] });
})();
