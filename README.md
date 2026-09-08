# LGD — Lower Garden District Properties

The web pages for a small New Orleans rental operation, plus a blank residential
lease that prints cleanly from any browser. A FastAPI service serves the pages,
gates the manager and admin areas behind HTTP Basic, and stores rental
applications and news.

E-signature is not part of this. The lease is printed and signed on paper.

## Layout

| Path | What it is |
| --- | --- |
| [documents/lease.md](documents/lease.md) | The **live** lease text. Edit this one. |
| [documents/application.md](documents/application.md) | The live rental application text. |
| [documents/lease_history.md](documents/lease_history.md) | What has changed in the lease, and when. A record — append, don't edit. |
| [documents/originals/](documents/originals/) | Frozen source material: the original scans and their verbatim transcripts. **Do not edit.** |
| [documents/print/](documents/print/) | `generate_print_lease.py` and the printable `lease_print.html` it produces |
| [index.html](index.html) | The public hub page — pick a role |
| [resident/](resident/), [applicant/](applicant/) | Public pages: contact details, and the rental application form |
| [login/](login/) | Sign in, create an account, reset a password |
| [manager/](manager/), [admin/](admin/) | Manager and admin areas — a signed-in manager or admin only |
| [shared/](shared/) | The footer, stylesheet, login client and account bar every page loads |
| [supabase/](supabase/) | SQL migrations for the Supabase database, and the script that applies them |
| [app/](app/) | FastAPI service: serves the pages, plus a small JSON API |
| [tests/](tests/) | Test suite. No network, no live database. |
| `accounts.json` | Managers and logins (local runs). Gitignored — created by `app.accounts`. Lives in Supabase Postgres instead when `DATABASE_URL` is set — see **Deploying** |

## Who uses this

| User | Role | Can act for |
| --- | --- | --- |
| Kevin Kolb | admin | every manager |
| Pam Hartnett | manager | LGD Properties |
| Gay Robertson | manager | Orange Street LLC |

A manager only sees their own company's records. The admin sees both.

Roles are stored as `admin` / `manager` / `resident`. Databases written before
those were renamed still hold `landlord` / `tenant`; both are accepted on load —
see `normalize_role` in [`app/config.py`](app/config.py).

## Setup

### 1. Install

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt  # macOS/Linux
```

### 2. Set up managers and logins

```bash
python -m app.accounts init
python -m app.accounts set-password kevin
python -m app.accounts set-password pam
python -m app.accounts set-password gay
```

`init` writes `accounts.json` with the two managers and three logins above; nobody
can log in until `set-password` is run for them. Passwords are stored only as a
PBKDF2-HMAC-SHA256 hash (600,000 iterations, random salt) — never in plaintext.
`python -m app.accounts list` shows who exists and whose password is set, without
printing any secret.

Basic auth base64-encodes credentials rather than encrypting them, so **serve this
behind HTTPS** anywhere but localhost.

`.env` is optional — everything defaults to local files. Copy `.env.example` if you
want to move storage somewhere else.

### 3. Run

```bash
.venv/Scripts/python.exe -m uvicorn app.main:app --reload
```

The hub page is at <http://localhost:8000/>, the manager dashboard at
<http://localhost:8000/manager/>.

## The printable lease

[`documents/print/lease_print.html`](documents/print/lease_print.html) is generated from
`documents/lease.md`. Regenerate it after any edit to the lease text:

```bash
python documents/print/generate_print_lease.py
```

It opens the browser's print dialog by itself. "Page X of Y" prints at the top and
bottom of every page, and the printed column is pinned to the paper width in
absolute units — without that, a phone lays the page out at its own screen width
and prints 9 pages where a desktop prints 6.

## Signing in

The live site is static files on GitHub Pages, with no server behind them, so
the login talks to **Supabase Auth** straight from the browser
([`shared/auth.js`](shared/auth.js), about 300 lines of `fetch` against
Supabase's REST endpoints — no bundler, no CDN script, nothing to keep up to
date). Anyone can create an account at [login/](login/); Supabase emails a link
to confirm the address, and only once that link is clicked does anything appear
in the database.

A new account is an **applicant**: a real login that can see its own details
and nothing else. Managers and admins are made by promoting one, not by signing
up. `role` and `manager_id` are not writable from a browser at all — no
row-level-security policy allows it.

Every login also has a row in `people`, always. `people` is the directory of
everyone the system knows about, and most of them never log in: an applicant
who filled in the form, a resident who has never signed in. Creating a login
creates the person; creating a person does not create a login.

### Setting this up on a fresh Supabase project

1. Apply the migration — this adds the link columns, the triggers, and row
   level security on every table:

   ```bash
   python supabase/apply_migrations.py
   ```

2. Paste the project's **publishable** key (Supabase dashboard ▸ Settings ▸
   API Keys) into `SUPABASE_PUBLISHABLE_KEY` in
   [`shared/auth.js`](shared/auth.js). That key is designed to be public and
   is safe to commit; the `sb_secret_…` key in `.env` is not, and must never
   go in a page.

3. In the dashboard, under Authentication:
   - **Keep "Confirm email" on.** The trigger that lets an existing account be
     claimed by its email address fires on confirmation, which is what makes
     "prove you can read that inbox" the price of claiming it.
   - Add the site's URL (and `…/login/`) to **URL Configuration ▸ Redirect
     URLs**, or the emailed links come back to the wrong place.

4. To let an account that predates all this be claimed by its owner, give it
   an email address. Signing up with that address then adopts the row — role,
   company and all — instead of creating a new applicant:

   ```bash
   python -m app.accounts set-email kevin kevin@example.com
   ```

## Deploying (Render + Supabase, free, no credit card)

Running this on a laptop needs nothing beyond the steps above — local SQLite and
`accounts.json` are all it uses, and that's what the test suite runs against too.
Putting it on the internet needs somewhere to run `uvicorn` continuously.
**Render's** free web-service tier does that at no cost, but its local disk does
not survive a restart — so records and logins move to **Supabase's** free Postgres
database, which does.

Which backend runs is decided entirely by environment variables — the app code
itself never needs to know or care:

| Storage | Local (laptop, tests) | Deployed (Render) |
| --- | --- | --- |
| Records | SQLite file (`LGD_DB_PATH`) | Supabase Postgres (`DATABASE_URL`) |
| Managers & logins | `accounts.json` | Supabase Postgres, same `DATABASE_URL` |
| Files | `archive/` folder (`LGD_ARCHIVE_DIR`) | Supabase Storage bucket (`LGD_ARCHIVE_DIR=supabase:<bucket>`) |

Nothing writes files yet — that half is kept ready for mail merge.

### One-time setup

1. **Supabase** — create a free project at supabase.com. From Project Settings ▸
   Database, copy the connection string (use the pooler/"Transaction" connection
   string, not the direct one) — that's `DATABASE_URL`. If you want the file
   storage, also copy the Project URL (`SUPABASE_URL`) and the **service_role** key
   (`SUPABASE_KEY`) from Project Settings ▸ API, and create a bucket under Storage
   — nothing in this app creates it for you.

2. **Populate accounts in Postgres**, from your own machine (Render's shell isn't
   part of the free tier, so do this locally, pointed at Supabase):

   ```bash
   export DATABASE_URL="<the Supabase connection string>"   # PowerShell: $env:DATABASE_URL="..."
   python -m app.accounts init
   python -m app.accounts set-password kevin
   ```

   With `DATABASE_URL` set, every `app.accounts` command operates on the Postgres
   `managers`/`webusers` tables instead of `accounts.json` — see `app/accounts.py`.

3. **Render** — create a free Web Service pointed at this GitHub repo.
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - Environment variables: `DATABASE_URL`, and if using file storage,
     `LGD_ARCHIVE_DIR=supabase:<bucket>` plus `SUPABASE_URL` and `SUPABASE_KEY`.

Render's free tier sleeps after 15 minutes of no traffic — the first request after
that takes a few seconds longer while it wakes up. Supabase's free database pauses
after 7 days of no activity too, but data is retained and resumes automatically on
the next connection. Neither requires a credit card.

## Terminology

The manager dashboard says **approved potential tenant**. The lease document says
**Lessee**. They are the same person — the code keeps the legal term where it feeds
the lease.

## Security

- Manager and admin areas need a signed-in manager or admin. On the live site
  that is Supabase Auth (see **Signing in**); when this app serves the pages it
  is HTTP Basic, with a PBKDF2 password hash and a timing-safe comparison
  against a decoy hash when the username doesn't exist — so an unknown user, a
  wrong password, and an account whose password lives in Supabase rather than
  here are all indistinguishable in both response and timing.
- The dashboard gate is an allow-list of roles (manager, admin), not "anyone
  who is not a resident". Anyone can sign up on the website, and a new signup
  is an `applicant`; an exclusion list would have let all of them in.
- Every table in Supabase is behind row level security. A browser holding the
  publishable key can read its own login row and its own person row, edit its
  own name and phone, and nothing else — it cannot change a role or a company.
  See [`supabase/migrations/`](supabase/migrations/).
- A manager can only see records for their own company; the API enforces this
  server-side regardless of what the browser sends. The admin can act for any.
- A management company's email address stays server-side. The browser sends a manager *id*; the
  server resolves the address.
- `.env`, `accounts.json`, `archive/`, and `*.db` are gitignored. No password hash
  is ever sent to the browser. The same applies to `DATABASE_URL` and
  `SUPABASE_KEY` when deployed — set only as Render environment variables, never
  committed.
- Static file serving resolves paths and rejects anything outside the directory it
  is serving.

The manager page used to ask for a shared password. That was a **deterrent, not
security** — the files are static and the repo is public, so viewing source
walked straight past it. It is gone, replaced by a real login. What renders in a
browser is still the browser's decision; the enforcement is row level security
in the database, which returns nothing to a signed-in applicant no matter what
their page chose to display.

## Tests

```bash
.venv/Scripts/python.exe -m pytest
```

No network and no live database: Postgres and Supabase Storage are exercised
against fakes, so the suite is free to run and safe offline.

## The lease text: two files, two purposes

`documents/originals/lease_transcript_verbatim.md` is a character-for-character transcript of
the original scanned paper lease. It is a historical record and is **not to be
edited** — ever.

`documents/lease.md` is the **live working copy**, meant to be edited over time as
the lease's actual terms change. It started identical to the verbatim transcript, and
is kept free of process notes and commentary so it stays a clean document to edit —
see [`CLAUDE.md`](CLAUDE.md) for that context instead. After editing it, regenerate
the printable lease with `python documents/print/generate_print_lease.py`.

The verbatim transcript preserves several original OCR-era wording quirks
("commended" for commenced, "solidarity" for solidarily, and others) that were
reviewed and deliberately corrected in `documents/lease.md` on 2026-09-06 — see
[`documents/lease_history.md`](documents/lease_history.md) for the full
before/after list, and for every change to the lease's terms since. Any further correction to the lease's
wording is a legal decision, not a find-and-replace: it belongs in
`documents/lease.md`, made deliberately, never silently.
