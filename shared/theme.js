"use strict";
/* The site's two main colors, as an admin chose them on the admin page
 * (the user, 2026-09-30). Loaded in the <head> of every site page, so it
 * runs before the page paints:
 *
 *   --accent   the main color: header bars, buttons, links (Tulane green)
 *   --accent2  the second color: the rule under each header, hovers, the
 *              staff buttons (Tulane light blue)
 *
 * With none chosen, nothing is set and each page keeps the colors in its
 * own stylesheet. Chosen colors are set on <html> itself, which outranks
 * those stylesheets (and the ?org=o orange scheme).
 *
 * The last colors seen are kept in this browser, applied at once so a page
 * never flashes the old ones, and then checked: from the FastAPI app's
 * /api/site-colors when it served the page, else from Supabase's
 * get_site_colors (supabase/migrations/005), which answers signed out.
 * The address and key below are shared/auth.js's - the key is the public,
 * publishable one, and a test keeps the two files in step. */
(function () {
  const SUPABASE_URL = "https://zglkceocuvioxovbnqrz.supabase.co";
  const SUPABASE_PUBLISHABLE_KEY = "sb_publishable_tqeV6Pt06bu6mNOEYBpHHw_f7GVm8qM";
  const CACHE = "lgd-site-colors";
  const COLOR = /^#[0-9a-f]{6}$/i;
  const VARIABLES = ["--accent", "--accent2", "--accent2-soft", "--accent-ink", "--ok"];

  const src = document.currentScript ? document.currentScript.src : window.location.href;
  const root = src.replace(/shared\/theme\.js(?:\?.*)?$/, "");

  function rgb(hex) {
    return [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  }

  // WCAG relative luminance, 0 (black) to 1 (white).
  function luminance(hex) {
    const [r, g, b] = rgb(hex).map((v) => {
      const c = v / 255;
      return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  }

  // Text on the main color: white unless the color is light enough that
  // dark ink reads better.
  function inkOn(hex) {
    const light = luminance(hex);
    return (1.05 / (light + 0.05)) >= ((light + 0.05) / 0.05) ? "#ffffff" : "#1c1c1a";
  }

  function valid(colors) {
    return colors && COLOR.test(colors.accent || "") && COLOR.test(colors.accent2 || "");
  }

  function apply(colors) {
    const style = document.documentElement.style;
    if (!valid(colors)) {
      for (const name of VARIABLES) style.removeProperty(name);
      return;
    }
    const [r, g, b] = rgb(colors.accent2);
    style.setProperty("--accent", colors.accent);
    style.setProperty("--accent2", colors.accent2);
    style.setProperty("--accent2-soft", `rgba(${r}, ${g}, ${b}, .35)`);
    style.setProperty("--accent-ink", inkOn(colors.accent));
    style.setProperty("--ok", colors.accent);
  }

  function remember(colors) {
    try {
      if (valid(colors)) localStorage.setItem(CACHE, JSON.stringify(colors));
      else localStorage.removeItem(CACHE);
    } catch (error) {
      /* Private browsing: the colors still apply, just not remembered. */
    }
  }

  function cached() {
    try {
      return JSON.parse(localStorage.getItem(CACHE) || "null");
    } catch (error) {
      return null;
    }
  }

  async function fetchColors() {
    try {
      const response = await fetch(root + "api/site-colors", { cache: "no-store" });
      if (response.ok && (response.headers.get("content-type") || "").includes("json")) {
        return await response.json();
      }
    } catch (error) {
      /* No FastAPI app here - the normal case on GitHub Pages. */
    }
    const response = await fetch(SUPABASE_URL + "/rest/v1/rpc/get_site_colors", {
      method: "POST",
      headers: {
        apikey: SUPABASE_PUBLISHABLE_KEY,
        Authorization: "Bearer " + SUPABASE_PUBLISHABLE_KEY,
        "Content-Type": "application/json",
      },
      body: "{}",
    });
    if (!response.ok) throw new Error("HTTP " + response.status);
    return response.json();
  }

  apply(cached());
  fetchColors()
    .then((colors) => {
      apply(colors);
      remember(colors);
    })
    .catch(() => {
      /* Offline, or the migration has not run: keep what is showing. */
    });

  // For the admin page: show a choice at once, and remember a saved one.
  window.LGD = window.LGD || {};
  window.LGD.theme = {
    apply,
    save(colors) {
      apply(colors);
      remember(colors);
    },
    inkOn,
    luminance,
    DEFAULTS: { accent: "#1f5d4c", accent2: "#71c5e8" },
  };
})();
