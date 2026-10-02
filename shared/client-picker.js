"use strict";
/* The company picker for the paper pages - the rent register, the rent
 * ledger, the Properties report and the legal pages - which have no
 * header bar, only floating buttons (.paper-buttons). The user,
 * 2026-10-02: "managers with multiple companies should be able to change
 * companies from any page". The header pages get theirs from
 * shared/home.js; this is the same picker, first among the floating
 * buttons. Load it after shared/auth.js.
 *
 * Only for a login linked to more than one company (list_my_clients,
 * supabase/migrations/008 and 012). Switching calls set_current_client,
 * remembers the company as "lgd-client" like home.js, and reloads - or,
 * where the page names one in <body data-after-switch="...">, goes there
 * (the ledger of one apartment goes back to its list, since the apartment
 * belongs to the other company). */
(function () {
  const CLIENT_KEY = "lgd-client";

  function remember(client) {
    try {
      localStorage.setItem(CLIENT_KEY, JSON.stringify({ id: client.id, name: client.name }));
    } catch (error) {
      /* not kept */
    }
  }

  async function run() {
    const auth = window.LGD && window.LGD.auth;
    const buttons = document.querySelector(".paper-buttons");
    if (!auth || !buttons || !(await auth.session())) return;
    let list;
    try {
      list = await auth.rpc("list_my_clients");
    } catch (error) {
      return;
    }
    if (!Array.isArray(list) || list.length < 2) return;
    const current = list.find((client) => client.current) || list[0];
    remember(current);

    const style = document.createElement("style");
    style.textContent = `
      .paper-buttons select.paper-client {
        font: inherit; font-size: 11pt; padding: 10px 34px 10px 16px; border-radius: 999px;
        border: 1px solid var(--accent, #006747); background-color: #fff; color: var(--accent, #006747);
        box-shadow: 0 3px 12px rgba(0, 0, 0, .25); max-width: 180px; cursor: pointer;
        -webkit-appearance: none; appearance: none;
        background-image: linear-gradient(45deg, transparent 50%, currentColor 50%),
                          linear-gradient(135deg, currentColor 50%, transparent 50%);
        background-position: right 19px center, right 14px center;
        background-size: 5px 5px; background-repeat: no-repeat;
      }
      @media (max-width: 600px) { .paper-buttons select.paper-client { max-width: 120px; } }
      @media print { .paper-buttons select.paper-client { display: none; } }`;
    document.head.append(style);

    const picker = document.createElement("select");
    picker.className = "paper-client";
    picker.setAttribute("aria-label", "Company");
    picker.title = "Switch company";
    for (const client of list) {
      const option = document.createElement("option");
      option.value = client.id;
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
        const next = document.body.getAttribute("data-after-switch");
        if (next) window.location.href = next;
        else window.location.reload();
      } catch (error) {
        picker.disabled = false;
        picker.value = current.id;
        window.alert(error.message || "That company could not be opened.");
      }
    });
    buttons.prepend(picker);
  }

  const start = () => run().catch(() => {});
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
