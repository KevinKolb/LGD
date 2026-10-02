"use strict";
/* Supabase Auth for this site, over plain fetch.
 *
 * Every page that needs to know who is signed in loads this one file:
 *
 *     <script src="../shared/auth.js"></script>
 *
 * and then uses `window.LGD.auth`. Nothing else on the page talks to
 * Supabase directly.
 *
 * WHY NOT supabase-js? The rest of this site has no third-party
 * dependencies at all - no build step, no bundler, no CDN script that has
 * to still be up for a login form to work. The four GoTrue endpoints below
 * are a stable, documented REST API, and using them directly keeps that
 * property. The cost is that token refresh is ours to get right; see
 * `session()`.
 *
 * WHAT CHECKS THE PASSWORD: Supabase Auth, not this app. The `password_hash`
 * column in the `users` table belongs to the FastAPI HTTP Basic path, which
 * is not what the live site uses - see CLAUDE.md.
 */

(function () {
  // -------------------------------------------------------------------------
  // Project configuration
  // -------------------------------------------------------------------------
  // The publishable key is *designed* to ship in a public page: it carries no
  // privileges of its own, and every table it can reach is behind row level
  // security (see supabase/migrations/001_auth_people_rls.sql). It is not the
  // `sb_secret_...` key from .env - that one bypasses RLS entirely and must
  // never appear in anything a browser downloads.
  const SUPABASE_URL = "https://zglkceocuvioxovbnqrz.supabase.co";
  const SUPABASE_PUBLISHABLE_KEY = "sb_publishable_tqeV6Pt06bu6mNOEYBpHHw_f7GVm8qM";

  const STORAGE_KEY = "lgd-auth";
  // Refresh this far before the token actually expires, so a request never
  // goes out holding a token that dies in flight.
  const REFRESH_MARGIN_SECONDS = 60;

  // This file's own URL locates the site root, so redirects work both at
  // https://kevinkolb.github.io/LGD/ and at http://localhost:8000/ without
  // anything being hardcoded. Same trick as shared/home.js.
  const scriptSrc = document.currentScript
    ? document.currentScript.src
    : window.location.href;
  const ROOT = scriptSrc.replace(/shared\/auth\.js(?:\?.*)?$/, "");

  const configured =
    SUPABASE_PUBLISHABLE_KEY && !SUPABASE_PUBLISHABLE_KEY.startsWith("REPLACE_");

  // -------------------------------------------------------------------------
  // Stored session
  // -------------------------------------------------------------------------

  function readStored() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (error) {
      // Private browsing, or a half-written value from an older version.
      return null;
    }
  }

  function writeStored(session) {
    try {
      if (session) localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
      else localStorage.removeItem(STORAGE_KEY);
    } catch (error) {
      /* Not remembering the session is survivable; this page still works. */
    }
  }

  /** Turn a GoTrue token response into what we actually store. */
  function toSession(body) {
    return {
      access_token: body.access_token,
      refresh_token: body.refresh_token,
      // Absolute, not a duration: a stored duration means nothing after the
      // tab has been closed for an hour.
      expires_at: Math.floor(Date.now() / 1000) + (body.expires_in || 3600),
      user: body.user || null,
    };
  }

  const listeners = [];

  function announce() {
    for (const listener of listeners) {
      try {
        listener();
      } catch (error) {
        /* one bad listener must not break the others */
      }
    }
  }

  // -------------------------------------------------------------------------
  // Requests
  // -------------------------------------------------------------------------

  class AuthError extends Error {}

  async function request(path, { method = "POST", body, token } = {}) {
    if (!configured) {
      throw new AuthError(
        "This site's Supabase key has not been filled in yet, so signing in " +
          "is not possible. See shared/auth.js."
      );
    }
    let response;
    try {
      response = await fetch(SUPABASE_URL + path, {
        method,
        headers: {
          apikey: SUPABASE_PUBLISHABLE_KEY,
          "Content-Type": "application/json",
          Authorization: "Bearer " + (token || SUPABASE_PUBLISHABLE_KEY),
        },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch (error) {
      throw new AuthError("Could not reach the server. Check your connection.");
    }
    const text = await response.text();
    const payload = text ? JSON.parse(text) : {};
    if (!response.ok) {
      // GoTrue puts the human-readable reason in one of several fields
      // depending on the endpoint and the error class.
      throw new AuthError(
        payload.error_description ||
          payload.msg ||
          payload.message ||
          payload.error ||
          `Request failed (HTTP ${response.status}).`
      );
    }
    return payload;
  }

  // -------------------------------------------------------------------------
  // Public API
  // -------------------------------------------------------------------------

  /** The current session, refreshed if it is about to expire. Null if signed out. */
  async function session() {
    const stored = readStored();
    if (!stored) return null;
    const secondsLeft = stored.expires_at - Math.floor(Date.now() / 1000);
    if (secondsLeft > REFRESH_MARGIN_SECONDS) return stored;

    try {
      const refreshed = toSession(
        await request("/auth/v1/token?grant_type=refresh_token", {
          body: { refresh_token: stored.refresh_token },
        })
      );
      writeStored(refreshed);
      return refreshed;
    } catch (error) {
      // A refresh token is single-use and rotates; once it is spent or
      // revoked there is no recovering the session, only signing in again.
      writeStored(null);
      announce();
      return null;
    }
  }

  async function signIn(email, password) {
    const result = toSession(
      await request("/auth/v1/token?grant_type=password", {
        body: { email: email.trim(), password },
      })
    );
    writeStored(result);
    announce();
    return result;
  }

  /**
   * Create an account. Returns { confirmationRequired } - with "Confirm
   * email" on in the project (which it must stay: see the migration's note
   * on why), no session comes back here, and nothing exists in `users` or
   * `people` until the emailed link is clicked.
   */
  // Said when an address is not in `people` yet (the user, 2026-09-29).
  const NOT_ON_FILE = "That email address is not yet on file.";

  /**
   * Whether this email address is already in `people` - someone a manager
   * added. Asked signed out (supabase/migrations/003's email_on_file), and
   * answers only yes or no.
   */
  async function emailOnFile(email) {
    return (await request("/rest/v1/rpc/email_on_file", { body: { email: (email || "").trim() } })) === true;
  }

  /**
   * Whether any property is accepting applications - yes or no, asked
   * signed out (supabase/migrations/004's accepting_applications). The
   * applicant page shows its Apply button only while it is.
   */
  async function acceptingApplications() {
    return (await request("/rest/v1/rpc/accepting_applications", { body: {} })) === true;
  }

  /**
   * Create a login - only for an address already on file; anyone else is
   * stopped here with NOT_ON_FILE, before Supabase sends any email. (001's
   * trigger holds the same line for a signup sent any other way.)
   */
  async function signUp(email, password, fullName, details) {
    if (!(await emailOnFile(email))) throw new AuthError(NOT_ON_FILE);
    const body = await request(
      "/auth/v1/signup?redirect_to=" + encodeURIComponent(ROOT + "login/"),
      {
        body: {
          email: email.trim(),
          password,
          // Lands in auth.users.raw_user_meta_data, which the database
          // trigger reads to name the person's row.
          // `details` - first_name, last_name, phone from the applicant
          // page - go the same way, and 001's trigger copies them onto
          // the person on file.
          data: { full_name: (fullName || "").trim(), ...(details || {}) },
        },
      }
    );
    if (body.access_token) {
      const result = toSession(body);
      writeStored(result);
      announce();
      return { confirmationRequired: false };
    }
    return { confirmationRequired: true };
  }

  async function signOut() {
    const stored = readStored();
    // Clear locally first, and unconditionally: if the network call fails,
    // "log out" still has to mean logged out on this device.
    writeStored(null);
    if (stored) {
      try {
        await request("/auth/v1/logout", { token: stored.access_token });
      } catch (error) {
        /* the token expires on its own soon enough */
      }
    }
    announce();
  }

  async function sendPasswordReset(email) {
    // Where the emailed link lands. This URL has to be listed under
    // Authentication > URL Configuration in the Supabase dashboard, or
    // Supabase ignores it and sends people to the project's Site URL.
    await request(
      "/auth/v1/recover?redirect_to=" + encodeURIComponent(ROOT + "login/"),
      { body: { email: email.trim() } }
    );
  }

  /** Set a new password for the signed-in session (including a recovery one). */
  async function updatePassword(newPassword) {
    const current = await session();
    if (!current) throw new AuthError("You are not signed in.");
    await request("/auth/v1/user", {
      method: "PUT",
      token: current.access_token,
      body: { password: newPassword },
    });
  }

  // Most senior first: `role` is the first of these a person holds.
  const ROLE_ORDER = ["admin", "manager", "resident", "applicant"];

  async function readRows(current, path) {
    const response = await fetch(SUPABASE_URL + "/rest/v1/" + path, {
      headers: {
        apikey: SUPABASE_PUBLISHABLE_KEY,
        Authorization: "Bearer " + current.access_token,
        Accept: "application/json",
      },
    });
    if (!response.ok) return null;
    return response.json();
  }

  /**
   * This person's row from the `people` table - everyone is one row there,
   * logins included, with a yes/no column per role (the user, 2026-09-29:
   * someone can be applicant and resident, or manager and admin). Row level
   * security limits the query to their own row, or none if the account has
   * not been confirmed yet.
   *
   * Returns { username, display_name, email, manager_id, person_id, roles,
   * role, role_label }: `roles` is every role held, `role` the most senior
   * one, `role_label` all of them for showing ("admin, manager").
   *
   * Until supabase/migrations/001 has merged the old `webusers` table into
   * `people`, the role columns do not exist and that query fails; the old
   * table is read instead, so signing in never waits on a migration.
   */
  async function profile() {
    const current = await session();
    if (!current) return null;
    let roles;
    let row;
    const people = await readRows(current,
      "people?select=id,username,full_name,email,manager_id," +
        "is_applicant,is_resident,is_manager,is_admin");
    if (people) {
      if (!people.length) return null;
      row = people[0];
      roles = ROLE_ORDER.filter((name) => row["is_" + name]);
      row = { username: row.username, display_name: row.full_name, email: row.email,
              manager_id: row.manager_id, person_id: row.id };
    } else {
      const old = await readRows(current,
        "webusers?select=username,display_name,role,manager_id,person_id,email");
      if (!old || !old.length) return null;
      const { role, ...rest } = old[0];
      row = rest;
      roles = [{ landlord: "manager", tenant: "resident" }[role] || role];
    }
    if (!roles.length) roles = ["applicant"];
    return { ...row, roles, role: roles[0], role_label: roles.join(", ") };
  }

  /**
   * Call one of the database's own functions (PostgREST /rest/v1/rpc/...)
   * as the signed-in person - e.g. create_applicant from the manager page.
   * The function itself checks who is calling and what they may do (see
   * supabase/migrations/002_manager_adds_applicants.sql); this only carries
   * the session. Throws AuthError with the database's own message, which
   * those functions word for the person reading it.
   */
  async function rpc(name, args) {
    const current = await session();
    if (!current) throw new AuthError("You have been signed out. Sign in again.");
    let response;
    try {
      response = await fetch(SUPABASE_URL + "/rest/v1/rpc/" + encodeURIComponent(name), {
        method: "POST",
        headers: {
          apikey: SUPABASE_PUBLISHABLE_KEY,
          Authorization: "Bearer " + current.access_token,
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify(args || {}),
      });
    } catch (error) {
      throw new AuthError("Could not reach the server. Check your connection.");
    }
    const text = await response.text();
    const payload = text ? JSON.parse(text) : null;
    if (!response.ok) {
      throw new AuthError(
        (payload && (payload.message || payload.hint)) ||
          `Request failed (HTTP ${response.status}).`
      );
    }
    return payload;
  }

  /**
   * Complete a link emailed by Supabase (confirmation, or password
   * recovery). Those links come back to the page with the tokens in the URL
   * *fragment*, which never reaches a server - which is exactly why this
   * works on GitHub Pages, where there is no server to receive them.
   *
   * Returns the link's type ("recovery", "signup", ...) or null if this page
   * was not opened from one. The fragment is wiped either way, so a password
   * reset token is not left sitting in the address bar or in history.
   */
  function consumeLinkFromUrl() {
    if (!window.location.hash || window.location.hash.length < 2) return null;
    const params = new URLSearchParams(window.location.hash.slice(1));
    const accessToken = params.get("access_token");
    const type = params.get("type");
    const errorDescription = params.get("error_description");

    if (!accessToken && !errorDescription) return null;

    history.replaceState(null, "", window.location.pathname + window.location.search);

    if (errorDescription) throw new AuthError(errorDescription);

    writeStored({
      access_token: accessToken,
      refresh_token: params.get("refresh_token"),
      expires_at:
        Math.floor(Date.now() / 1000) + Number(params.get("expires_in") || 3600),
      user: null,
    });
    announce();
    return type || "signup";
  }

  /**
   * Send the browser to the login page, remembering where it was headed so
   * the login page can send it back afterwards.
   */
  function goToLogin() {
    const next = window.location.href;
    window.location.href = ROOT + "login/?next=" + encodeURIComponent(next);
  }

  /**
   * Page gate. Resolves to one of:
   *
   *   { ok: true,  profile }              - let them in
   *   { ok: false, reason: "signed-out" } - nobody is signed in (this has
   *                                         already started navigating to
   *                                         the login page)
   *   { ok: false, reason: "unconfirmed" }- signed in, but no `people` row
   *                                         yet, so the emailed link has
   *                                         not been clicked
   *   { ok: false, reason: "forbidden", profile } - signed in as someone
   *                                         holding none of the roles this
   *                                         page needs
   *
   * The three failures are deliberately distinct: telling a signed-in
   * applicant "you do not have access" is right, while bouncing them to a
   * login form they have already filled in is maddening.
   */
  async function requireRole(roles) {
    const current = await session();
    if (!current) {
      goToLogin();
      return { ok: false, reason: "signed-out" };
    }
    const who = await profile();
    if (!who) return { ok: false, reason: "unconfirmed" };
    if (!who.roles.some((role) => roles.includes(role))) {
      return { ok: false, reason: "forbidden", profile: who };
    }
    return { ok: true, profile: who };
  }

  window.LGD = window.LGD || {};
  window.LGD.auth = {
    AuthError,
    configured,
    root: ROOT,
    session,
    signIn,
    signUp,
    signOut,
    sendPasswordReset,
    updatePassword,
    profile,
    emailOnFile,
    acceptingApplications,
    NOT_ON_FILE,
    rpc,
    consumeLinkFromUrl,
    requireRole,
    goToLogin,
    onChange(listener) {
      listeners.push(listener);
    },
  };
})();
