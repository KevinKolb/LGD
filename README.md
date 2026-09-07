# LGD — Lower Garden District Properties

Lease signing automation. A landlord fills out a form, the app fills the blanks in
the standard residential lease, sends it to PandaDoc for signature, and hands back a
link to give the approved potential tenant. PandaDoc webhooks keep the status
current and archive the executed PDF once it's signed.

## Layout

| Path | What it is |
| --- | --- |
| [originals/lease.md](originals/lease.md) | The **live** lease text. Edit this one. |
| [originals/lease_transcript_verbatim.md](originals/lease_transcript_verbatim.md) | The original scan, transcribed verbatim. **Do not edit.** |
| [pandadoc/](pandadoc/) | One-time PandaDoc setup and the template body to paste in |
| [landlord/](landlord/) | The dashboard — a single static page behind HTTP Basic |
| [app/](app/) | FastAPI service: JSON API, PandaDoc client, webhook receiver |
| [tests/](tests/) | Test suite. Stubs PandaDoc, so it never spends a document |
| `accounts.json` | Landlords and logins (local runs). Gitignored — created by `app.accounts`. Lives in Supabase Postgres instead when `DATABASE_URL` is set — see **Deploying** below |
| `archive/` | Executed lease PDFs (local runs), saved as each one is signed. Gitignored. Lives in Supabase Storage instead when `LGD_ARCHIVE_DIR` names a `supabase:` bucket |

## Who uses this

| User | Role | Can act for |
| --- | --- | --- |
| Kevin Kolb | admin | every landlord |
| Pam Hartnett | landlord | LGD Properties |
| Gay Robertson | landlord | Orange Street LLC |

A landlord user only ever sees and creates leases for their own company. The admin
sees and can act for both. See [pandadoc/TEMPLATE_SETUP.md](pandadoc/TEMPLATE_SETUP.md)
step 6 for setting these up.

## Sandbox vs production

The PandaDoc account has a sandbox key (free, unlimited, **not legally binding**) and
a production key (real documents, capped at **60 per year**, non-refundable once
created). `PANDADOC_MODE` in `.env` picks which one the app talks to, and **defaults
to `sandbox`** so that spending a real document is a deliberate switch, not an
accident.

The dashboard shows a banner whenever it's in sandbox mode, and every lease created
there is tagged **Sandbox** in the leases list, permanently, so a test run can never
be mistaken for a real lease later.

Use sandbox for all routine work and testing. [pandadoc/TEMPLATE_SETUP.md](pandadoc/TEMPLATE_SETUP.md)
covers switching to production for the one real lease that proves the path end to end.

## Setup

### 1. Install

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt   # Windows
# source .venv/bin/activate && pip install -r requirements-dev.txt  # macOS/Linux
```

### 2. Configure PandaDoc

Work through [pandadoc/TEMPLATE_SETUP.md](pandadoc/TEMPLATE_SETUP.md) in full. It
produces the sandbox and production API keys, the template UUID(s), and the webhook
shared key.

```bash
cp .env.example .env
```

### 3. Set up landlords and logins

```bash
python -m app.accounts init
python -m app.accounts set-password kevin
python -m app.accounts set-password pam
python -m app.accounts set-password gay
```

`init` writes `accounts.json` with the two landlords and three users above; nobody
can log in until `set-password` is run for them. Passwords are stored only as a
PBKDF2-HMAC-SHA256 hash (600,000 iterations, random salt) — never in plaintext.
`python -m app.accounts list` shows who exists and whose password is set, without
printing any secret.

Basic auth base64-encodes credentials rather than encrypting them, so **serve this
behind HTTPS** anywhere but localhost. PandaDoc also requires an HTTPS webhook
endpoint regardless.

### 4. Run

```bash
.venv/Scripts/python.exe -m uvicorn app.main:app --reload
```

The dashboard is at <http://localhost:8000/landlord/>.

## Deploying (Render + Supabase, free, no credit card)

Running this on a laptop needs nothing beyond the steps above — local SQLite,
`accounts.json`, and a local `archive/` folder are all it uses, and that's exactly
what the test suite runs against too. Putting it on the actual internet needs
somewhere to run `uvicorn` continuously, which a laptop doesn't do. **Render's**
free web-service tier does that at no cost, but its local disk does not survive a
restart — so leases, logins, and archived PDFs all move to **Supabase's** free
Postgres database and Storage bucket instead, which do survive.

Which backend runs is decided entirely by environment variables — the app code
itself never needs to know or care:

| Storage | Local (laptop, tests) | Deployed (Render) |
| --- | --- | --- |
| Leases | SQLite file (`LGD_DB_PATH`) | Supabase Postgres (`DATABASE_URL`) |
| Landlords & logins | `accounts.json` | Supabase Postgres, same `DATABASE_URL` |
| Signed PDFs | `archive/` folder (`LGD_ARCHIVE_DIR`) | Supabase Storage bucket (`LGD_ARCHIVE_DIR=supabase:<bucket>`) |

### One-time setup

1. **Supabase** — create a free project at supabase.com. From Project Settings ▸
   Database, copy the connection string (use the pooler/"Transaction" connection
   string, not the direct one) — that's `DATABASE_URL`. From Project Settings ▸
   API, copy the Project URL (`SUPABASE_URL`) and the **service_role** key
   (`SUPABASE_KEY`) — not the anon key; the dashboard is the only thing writing to
   the bucket and already enforces its own login. Under Storage, create a bucket
   (e.g. `signed-leases`) — nothing in this app creates it for you.

2. **Populate accounts in Postgres**, from your own machine (Render's shell isn't
   part of the free tier, so do this locally, pointed at Supabase):

   ```bash
   export DATABASE_URL="<the Supabase connection string>"   # PowerShell: $env:DATABASE_URL="..."
   python -m app.accounts init
   python -m app.accounts set-password kevin
   python -m app.accounts set-password pam
   python -m app.accounts set-password gay
   ```

   With `DATABASE_URL` set, every `app.accounts` command operates on the Postgres
   `landlords`/`users` tables instead of `accounts.json` — see `app/accounts.py`.

3. **Render** — create a free Web Service pointed at this GitHub repo.
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - Environment variables: everything in `.env.example` (all the `PANDADOC_*`
     ones, the webhook shared key), plus:
     - `DATABASE_URL` = the same Supabase connection string as above
     - `LGD_ARCHIVE_DIR` = `supabase:signed-leases` (your bucket name)
     - `SUPABASE_URL`, `SUPABASE_KEY` = from step 1

4. Update the PandaDoc webhook's endpoint URL (see
   [pandadoc/TEMPLATE_SETUP.md](pandadoc/TEMPLATE_SETUP.md) step 5) to point at the
   Render URL instead of a local tunnel.

Render's free tier sleeps after 15 minutes of no traffic — the first request after
that takes a few seconds longer while it wakes up. Supabase's free database pauses
after 7 days of no activity too, but data is retained and resumes automatically on
the next connection. Neither requires a credit card.

## How a lease flows

1. The landlord signs in, picks their Lessor (or, for the admin, any Lessor), enters
   the property, the approved potential tenants, the term, and the money, then
   presses **Preview** to check the filled blanks — free, and contacts nothing.
2. **Generate lease** creates the document from the PandaDoc template, waits for it
   to leave `document.uploaded`, and sends it with `silent: true` — sealed for
   signing, but PandaDoc emails nobody.
3. The app pulls the primary tenant's `shared_link` from the document details and
   returns it. That URL does not expire. If it is unavailable, the app falls back to
   an embedded-signing session link, which does expire (14 days by default).
4. The landlord copies the link, or uses the pre-filled mail draft.
5. PandaDoc posts status changes to `/webhooks/pandadoc`; the dashboard reflects them.
6. Once the document is completed, the app downloads the executed PDF and saves it
   under `archive/`. The leases list gets a **Download** link for it — the app fetches
   it on demand if the webhook hasn't archived it yet.

Set `PANDADOC_SENDS_EMAIL=true` to have PandaDoc email the tenant directly as well —
that also enables its automatic signing reminders.

### Who signs

The landlord's **company** fills the lease's Lessor blank; the landlord's own name
signs it, matching the paper lease's "Lessor/Agent" signature line. The landlord
signs first (`signing_order` 1), then all tenants (`signing_order` 2). Roles in the
template must be named `Lessor`, `Lessee`, `Lessee2`, `Lessee3`.

## Terminology

The dashboard says **approved potential tenant**. The lease document says **Lessee**.
They are the same person — the code keeps the legal term because those values feed a
legal instrument.

## Security

- Dashboard and API behind HTTP Basic; PBKDF2 password hash; timing-safe comparison
  against a decoy hash when the username doesn't exist, so an unknown user and a
  wrong password are indistinguishable in both response and timing.
- A landlord-role user can only create, list, or download leases for their own
  landlord; the API enforces this server-side regardless of what the browser sends.
  The admin role can act for any landlord.
- The webhook is exempt from Basic auth (PandaDoc cannot send credentials) and is
  instead verified by HMAC-SHA256 over the **raw** request body against the shared
  key, with a 403 on mismatch.
- Landlord email addresses stay server-side. The browser sends a landlord *id*; the
  server resolves the address, so a tampered request cannot redirect the Lessor copy.
- `.env`, `accounts.json`, `archive/`, and `*.db` are gitignored. No API key or
  password hash is ever sent to the browser. The same applies to `DATABASE_URL` and
  `SUPABASE_KEY` when deployed (see **Deploying** below) — set only as Render
  environment variables, never committed.
- Static file serving resolves paths and rejects anything outside `landlord/`.
- Executed PDFs are downloaded from PandaDoc's `download-protected` endpoint in
  production (sandbox falls back to the plain `download` endpoint, since
  `download-protected` requires a production key and 401s on a sandbox one).

Anyone holding a signing link can sign as that recipient — treat those links like
passwords and send them to the tenant directly, not to a shared inbox.

## Tests

```bash
.venv/Scripts/python.exe -m pytest
```

PandaDoc is stubbed throughout, so the suite is free to run and safe offline.

## The lease text: two files, two purposes

`originals/lease_transcript_verbatim.md` is a character-for-character transcript of
the original scanned paper lease. It is a historical record and is **not to be
edited** — ever.

`originals/lease.md` is the **live working copy**, meant to be edited over time as
the lease's actual terms change. It started identical to the verbatim transcript, and
is kept free of process notes and commentary so it stays a clean document to edit —
see [`CLAUDE.md`](CLAUDE.md) for that context instead.
[`pandadoc/lease_template_body.md`](pandadoc/lease_template_body.md) is a
**generated file** (blanks replaced by PandaDoc tokens), produced by
[`pandadoc/generate_template_body.py`](pandadoc/generate_template_body.py) — never
edit it directly. After editing `originals/lease.md`, run
`python pandadoc/generate_template_body.py` and re-paste the result into PandaDoc.

The verbatim transcript preserves several original OCR-era wording quirks
("commended" for commenced, "solidarity" for solidarily, and others) that were
reviewed and deliberately corrected in `originals/lease.md` on 2026-09-06 — see
`CLAUDE.md` for the full before/after list. Any further correction to the lease's
wording is a legal decision, not a find-and-replace: it belongs in
`originals/lease.md`, made deliberately, never silently.
