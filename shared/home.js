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
    .hdr-home, header.site-header #account-toggle, .hdr-client {
      box-sizing: border-box; height: 36px; border-radius: 999px;
      border: 1px solid rgba(255, 255, 255, .45); background: rgba(255, 255, 255, .1);
      color: inherit; font: inherit; font-size: 13px; font-weight: 600; line-height: 1;
      letter-spacing: .04em; cursor: pointer;
    }
    .hdr-home {
      order: 1; flex: none; display: inline-flex; align-items: center; gap: 8px;
      padding: 0 16px 0 5px; text-decoration: none; text-transform: uppercase;
    }
    .hdr-home img {
      width: 26px; height: 26px; padding: 3px; box-sizing: border-box;
      border-radius: 50%; background: #fff;
    }
    header.site-header #account-toggle {
      min-width: 92px; padding: 0 16px; text-transform: uppercase;
    }
    .hdr-home:hover, header.site-header #account-toggle:hover, .hdr-client:hover {
      background: rgba(255, 255, 255, .22);
    }
    .hdr-client {
      margin: 0; width: auto; max-width: 230px; padding: 0 30px 0 14px; text-overflow: ellipsis;
      -webkit-appearance: none; appearance: none;
      background-image: linear-gradient(45deg, transparent 50%, currentColor 50%),
                        linear-gradient(135deg, currentColor 50%, transparent 50%);
      background-position: right 16px center, right 11px center;
      background-size: 5px 5px; background-repeat: no-repeat;
    }
    .hdr-client option { color: #1c1c1a; background: #fff; }
    /* A phone: Home and the buttons on top, the titles beneath, full width. */
    @media (max-width: 600px) {
      header.site-header { padding: 12px 16px 16px; gap: 14px 10px; }
      header.site-header .hdr-titles { order: 4; flex-basis: 100%; }
      header.site-header .hdr-actions { order: 2; }
      header.site-header .hdr-actions { gap: 8px; }
      .hdr-home, header.site-header #account-toggle, .hdr-client { height: 34px; font-size: 12px; }
      .hdr-home { gap: 6px; padding: 0 12px 0 4px; }
      .hdr-home img { width: 24px; height: 24px; }
      header.site-header #account-toggle { min-width: 0; padding: 0 12px; }
      .hdr-client { max-width: 96px; padding: 0 24px 0 10px; background-position: right 14px center, right 9px center; }
    }
    /* A page with no header bar (sign-in): Home floats in the corner. */
    .hdr-home.floating {
      position: fixed; top: 16px; left: 16px; z-index: 20;
      border-color: var(--accent, #1f5d4c); color: var(--accent, #1f5d4c); background: #fff;
    }
    @media print { .hdr-home, .hdr-actions { display: none; } }`;
  document.head.append(style);

  const home = document.createElement("a");
  home.className = "hdr-home";
  home.id = "home-button";
  home.href = root;
  const icon = document.createElement("img");
  icon.src = root + "shared/icons/house.svg";
  icon.alt = "";
  home.append(icon, "Home");

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
  header.classList.add("site-header");
  header.append(home, titles, actions);
  // Login/Logout (shared/account.js) belongs with the buttons, wherever
  // and whenever it lands in the header.
  const placeAccount = () => {
    const bar = document.getElementById("account-bar");
    if (bar && bar.parentNode !== actions) actions.append(bar);
  };
  placeAccount();
  new MutationObserver(placeAccount).observe(header, { childList: true, subtree: true });

  // The current client's name, wherever the page asks for it.
  function showClient(client) {
    if (!client || !client.name) return;
    for (const line of document.querySelectorAll(".company[data-client]")) {
      line.textContent = client.name;
    }
  }
  function remember(client) {
    try {
      localStorage.setItem(CLIENT_KEY, JSON.stringify({ id: client.id, name: client.name }));
    } catch (error) {
      /* Private browsing: the name just is not carried to other pages. */
    }
  }
  try {
    showClient(JSON.parse(localStorage.getItem(CLIENT_KEY) || "null"));
  } catch (error) {
    /* Nothing remembered yet. */
  }

  async function clients() {
    const auth = window.LGD && window.LGD.auth;
    if (!auth || !(await auth.session())) return;
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
    if (list.length < 2 || !document.getElementById("account-bar")) return;

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
  }
  clients();
})();
