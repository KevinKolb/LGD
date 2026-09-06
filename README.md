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
| `accounts.json` | Landlords and logins. Gitignored — created by `app.accounts` |
| `archive/` | Executed lease PDFs, saved as each one is signed. Gitignored |

## Who uses this

| User | Role | Can act for |
| --- | --- | --- |
| Kevin Kolb | admin | every landlord |
| Steve Hartnett | landlord | LGD Properties |
| Gay Robertson | landlord | Gay Robertson Properties |

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
python -m app.accounts set-password steve
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
  password hash is ever sent to the browser.
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
