"use strict";
/* The header of the main pages - applicant, resident, manager, admin - and
 * Home on the sign-in page. Loaded just before </body>, after
 * shared/account.js where a page has it; not on the home page itself.
 *
 * The user, 2026-10-02: no footer ("really just need a back button in
 * upper right"), then "rename back to home and put it in a better place",
 * "logout and back buttons same size" and "make the header better man,
 * cmon". It replaced shared/footer.js (deleted) and, briefly, back.js.
 *
 * The page's own <header> keeps its text; this lays it out as one bar:
 *
 *   [ (house) HOME ]  CLIENT NAME                [ Client v ] [ LOGOUT ]
 *                     Page title
 *
 * Home always goes to the home page. On a phone the buttons take the top
 * row and the titles the full width beneath. Signed in, the client picker
 * (supabase/migrations/008) lists the clients the login is linked to - only
 * when there is more than one - and switching reloads the page in that
 * client. The current client's name fills any `.company[data-client]`, and
 * is kept in this browser ("lgd-client") for the rent register and the
 * printed documents. */

(function () {
  // The site root, from this script's own URL: GitHub Pages serves the
  // site under /LGD/, the FastAPI app at the domain root.
  const src = document.currentScript ? document.currentScript.src : window.location.href;
  const root = src.replace(/shared\/home\.js(?:\?.*)?$/, "");
  const CLIENT_KEY = "lgd-client";

  const style = document.createElement("style");
  style.textContent = `
    header.site-header {
      display: flex; align-items: center; gap: 14px 18px; flex-wrap: wrap;
      padding: 14px 24px; position: static;
    }
    header.site-header .hdr-titles { flex: 1 1 260px; min-width: 0; order: 2; }
    header.site-header .hdr-titles > div { margin: 0; }
    header.site-header .company {
      margin: 0; font-size: 12px; font-weight: 600; opacity: .85;
      letter-spacing: .06em; text-transform: uppercase;
    }
    header.site-header h1 {
      margin: 1px 0 0; font-size: 21px; line-height: 1.2; font-weight: 700;
      letter-spacing: .01em; text-transform: none;
    }
    header.site-header .hdr-titles p:not(.company) { margin: 2px 0 0; font-size: 13px; opacity: .8; }
    header.site-header .hdr-actions {
      order: 3; margin-left: auto; display: flex; align-items: center; gap: 10px;
    }
    header.site-header .hdr-home, header.site-header #account-toggle, header.site-header .hdr-client {
      box-sizing: border-box; height: 36px; border-radius: 999px;
      border: 1px solid rgba(255, 255, 255, .45); background: rgba(255, 255, 255, .1);
      color: inherit; font: inherit; font-size: 13px; font-weight: 600; line-height: 1;
      letter-spacing: .04em; cursor: pointer;
    }
    .hdr-home {
      order: 1; flex: none; display: inline-flex; align-items: center; gap: 8px;
      padding: 0 16px 0 5px; text-decoration: none; text-transform: uppercase;
    }
    .hdr-home .hdr-arrow { font-size: 20px; line-height: 1; padding-left: 9px; margin-top: -2px; }
    .hdr-gear {
      box-sizing: border-box; width: 36px; height: 36px; flex: none;
      display: inline-flex; align-items: center; justify-content: center;
      border-radius: 50%; border: 1px solid rgba(255, 255, 255, .45);
      background: rgba(255, 255, 255, .1); color: inherit;
    }
    .hdr-gear:hover { background: rgba(255, 255, 255, .22); }
    .hdr-home img {
      width: 26px; height: 26px; padding: 3px; box-sizing: border-box;
      border-radius: 50%; background: #fff;
    }
    header.site-header #account-toggle {
      min-width: 92px; padding: 0 16px; text-transform: uppercase;
    }
    header.site-header .hdr-home:hover, header.site-header #account-toggle:hover, header.site-header .hdr-client:hover {
      background-color: rgba(255, 255, 255, .22);
    }
    header.site-header .hdr-client {
      margin: 0; width: auto; max-width: 230px; padding: 0 30px 0 14px; text-overflow: ellipsis;
      -webkit-appearance: none; appearance: none;
      background-image: linear-gradient(45deg, transparent 50%, currentColor 50%),
                        linear-gradient(135deg, currentColor 50%, transparent 50%);
      background-position: right 16px center, right 11px center;
      background-size: 5px 5px; background-repeat: no-repeat;
    }
    header.site-header .hdr-client option { color: #1c1c1a; background: #fff; }
    /* A phone: Home and the buttons on top, the titles beneath, full width. */
    @media (max-width: 600px) {
      header.site-header { padding: 12px 16px 16px; gap: 14px 10px; }
      header.site-header .hdr-titles { order: 4; flex-basis: 100%; }
      /* No Home on the home page: the title and Login/Logout share a row. */
      header.site-header[data-no-home] .hdr-titles { order: 1; flex: 1 1 0; }
      header.site-header .hdr-actions { order: 2; }
      header.site-header .hdr-actions { gap: 8px; }
      header.site-header .hdr-home, header.site-header #account-toggle, header.site-header .hdr-client { height: 34px; font-size: 12px; }
      .hdr-home { gap: 6px; padding: 0 12px 0 4px; }
      .hdr-home img { width: 24px; height: 24px; }
      header.site-header #account-toggle { min-width: 0; padding: 0 12px; }
      header.site-header .hdr-client { max-width: 96px; padding: 0 24px 0 10px; background-position: right 14px center, right 9px center; }
      /* Picker, gear and Logout as well (a two-site manager): Home keeps
         its house and drops the word, so they all still fit one row. */
      header.site-header.crowded .hdr-home .hdr-label { display: none; }
      header.site-header.crowded .hdr-home { padding: 0 4px; }
      header.site-header .hdr-gear { width: 34px; height: 34px; }
    }
    /* A page with no header bar (sign-in): Home floats in the corner. */
    .hdr-home.floating {
      position: fixed; top: 16px; left: 16px; z-index: 20;
      border-color: var(--accent, #1f5d4c); color: var(--accent, #1f5d4c); background: #fff;
    }
    header.site-header #account-bar[hidden] { display: none !important; }
    @media print { .hdr-home, .hdr-actions { display: none; } }`;
  document.head.append(style);

  const home = document.createElement("a");
  home.className = "hdr-home";
  home.id = "home-button";
  home.href = root;
  const icon = document.createElement("img");
  icon.src = root + "shared/icons/house.svg";
  icon.alt = "";
  const label = document.createElement("span");
  label.className = "hdr-label";
  label.textContent = "Home";
  home.append(icon, label);

  const header = document.querySelector("header:not(.site-title)");
  if (!header) {
    home.classList.add("floating");
    document.body.append(home);
    return;
  }

  const titles = document.createElement("div");
  titles.className = "hdr-titles";
  titles.append(...header.childNodes);
  const actions = document.createElement("div");
  actions.className = "hdr-actions";
  // The admin page is reached from the manager page's gear, so its way out
  // is Back to the Manager Portal rather than Home (data-up="<path>").
  const up = header.getAttribute("data-up");
  if (up) {
    home.href = root + up;
    label.textContent = "Back";
    icon.remove();
    home.prepend(Object.assign(document.createElement("span"), { className: "hdr-arrow", textContent: "‹" }));
  }
  // A gear for the settings page, beside Logout (data-gear="<path>"; the
  // user, 2026-10-02: the admin page "is accessible through a gear button
  // on manager page").
  const gearPath = header.getAttribute("data-gear");
  if (gearPath) {
    const gear = document.createElement("a");
    gear.className = "hdr-gear";
    gear.href = root + gearPath;
    gear.title = "Settings";
    gear.setAttribute("aria-label", "Settings");
    gear.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none" ' +
      'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
      '<circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 ' +
      '2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 ' +
      '19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 ' +
      '0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-' +
      '2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 ' +
      '1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 ' +
      '1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>';
    actions.append(gear);
  }

  header.classList.add("site-header");
  // The home page's header has no Home (data-no-home): it is home.
  if (header.hasAttribute("data-no-home")) header.append(titles, actions);
  else header.append(home, titles, actions);
  // Login/Logout (shared/account.js) belongs with the buttons, wherever
  // and whenever it lands in the header.
  const placeAccount = () => {
    const bar = document.getElementById("account-bar");
    if (bar && bar.parentNode !== actions) actions.append(bar);
    // The home page shows Logout when someone is signed in, and no Login
    // (the user, 2026-10-02: "no login on home page, only logoff if
    // necessary") - signing in starts from a role's button.
    if (bar && header.hasAttribute("data-no-home")) bar.hidden = !signedInHere();
    // The gear sits just left of Login/Logout.
    const gear = actions.querySelector(".hdr-gear");
    if (gear && bar && gear.nextElementSibling !== bar) actions.insertBefore(gear, bar);
  };
  placeAccount();
  new MutationObserver(placeAccount).observe(header, { childList: true, subtree: true });

  // The name at the top of every page, and in the browser tab:
  // "momandpop.com" until a signed-in login's client is known, then that
  // client's name (the user, 2026-10-02). Each page marks it data-client -
  // the home page's title, the company line above the others' titles.
  const BRAND = "momandpop.com";
  const pageTitle = document.title;
  function showClient(client) {
    const name = (client && client.name) || BRAND;
    for (const line of document.querySelectorAll("[data-client]")) {
      line.textContent = name;
    }
    document.title = header.hasAttribute("data-no-home") || pageTitle === BRAND
      ? name : pageTitle + " - " + name;
  }
  function signedInHere() {
    try {
      return Boolean(localStorage.getItem("lgd-auth"));
    } catch (error) {
      return false;
    }
  }
  function forget() {
    try {
      localStorage.removeItem(CLIENT_KEY);
    } catch (error) {
      /* nothing kept */
    }
  }
  function remember(client) {
    try {
      localStorage.setItem(CLIENT_KEY, JSON.stringify({ id: client.id, name: client.name }));
    } catch (error) {
      /* Private browsing: the name just is not carried to other pages. */
    }
  }
  // At once, from what this browser remembers - only while signed in.
  let remembered = null;
  try {
    remembered = signedInHere() ? JSON.parse(localStorage.getItem(CLIENT_KEY) || "null") : null;
  } catch (error) {
    /* Nothing remembered yet. */
  }
  if (!signedInHere()) forget();
  showClient(remembered);

  // A welcome under the title on every page (the user, 2026-10-02: "put a
  // generic welcome message under page title, personalized if login"):
  // "Welcome." signed out, "Welcome back, Kevin (manager)." signed in, with
  // the roles held (the user, same day: "just put role in welcome
  // messages"; an admin reads as manager, one credential). The manager
  // page's own line (#whoami) is used where there is one.
  let welcome = titles.querySelector("#whoami");
  if (!welcome) {
    welcome = document.createElement("p");
    welcome.className = "hdr-welcome";
    const title = titles.querySelector("h1");
    if (title) title.after(welcome);
    else titles.append(welcome);
  }
  welcome.textContent = signedInHere() ? "" : "Welcome.";
  async function greet(auth) {
    let who = null;
    try {
      who = await auth.profile();
    } catch (error) {
      /* The login service did not answer: a plain welcome. */
    }
    const first = who ? String(who.display_name || "").trim().split(/[ ]+/)[0] : "";
    // A name that is still an email (an applicant who has not signed up
    // yet has their email there) is no name to greet.
    const held = who && Array.isArray(who.roles) ? who.roles : [];
    const roles = ["manager", "resident", "applicant"].filter((role) =>
      held.indexOf(role) >= 0 || (role === "manager" && held.indexOf("admin") >= 0));
    const label = roles.length ? " (" + roles.join(", ") + ")" : "";
    welcome.textContent = first && first.indexOf("@") < 0
      ? "Welcome back, " + first + label + "."
      : "Welcome back" + label + ".";
  }

  async function clients() {
    const auth = window.LGD && window.LGD.auth;
    if (!auth) return;
    if (!(await auth.session())) {
      forget();
      showClient(null);
      welcome.textContent = "Welcome.";
      const bar = document.getElementById("account-bar");
      if (bar && header.hasAttribute("data-no-home")) bar.hidden = true;
      return;
    }
    greet(auth);
    let list;
    try {
      list = await auth.rpc("list_my_clients");
    } catch (error) {
      return;   // 008 not applied yet, or signed out: the page's own text stays
    }
    if (!Array.isArray(list) || !list.length) return;
    const current = list.find((client) => client.current) || list[0];
    remember(current);
    showClient(current);
    // The picker is for the staff pages, the ones with Login/Logout.
    // The picker is for the staff pages (header data-client-picker), and
    // only for a login linked to more than one client.
    if (list.length < 2 || !header.hasAttribute("data-client-picker")) return;

    const picker = document.createElement("select");
    picker.className = "hdr-client";
    picker.setAttribute("aria-label", "Client");
    picker.title = "Switch client";
    for (const client of list) {
      const option = document.createElement("option");
      option.value = client.id;
      // Short in the picker - "LGD", "Orange Street" - since the full
      // name is the line above the title.
      option.textContent = client.name.split(" (")[0].replace(/,? Inc\.?$/, "");
      option.selected = client.id === current.id;
      picker.append(option);
    }
    picker.addEventListener("change", async () => {
      picker.disabled = true;
      try {
        const updated = await auth.rpc("set_current_client", { client: picker.value });
        const now = (updated || []).find((client) => client.current);
        if (now) remember(now);
        window.location.reload();
      } catch (error) {
        picker.disabled = false;
        picker.value = current.id;
        window.alert(error.message || "That client could not be opened.");
      }
    });
    actions.prepend(picker);
    if (actions.querySelector(".hdr-gear")) header.classList.add("crowded");
  }
  clients();
})();
