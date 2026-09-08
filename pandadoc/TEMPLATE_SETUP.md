# PandaDoc setup

One-time setup. Work through it in order; most steps produce a value that goes in
`.env` — step 6 (landlords and logins) goes in `accounts.json` instead. Nothing in
this repo can run until steps 2, 4, 5 and 6 are done.

---

## 1. The account

Registered to `KevinMKolb@gmail.com`, free plan, **60 documents per year**, with a
production API key **and a sandbox key**.

The production allowance is the thing to design around. Sandbox documents are free
and unlimited, but they are **not legally binding** — do not send a sandbox link to a
real tenant expecting to sign a real lease. Every production document, by contrast,
permanently spends one of the 60 — including mistakes, throwaway tests, and a lease
you void a minute later. Voiding does not refund it.

This app defaults to **sandbox mode** (`PANDADOC_MODE=sandbox` in `.env`) so that
spending a real document is a deliberate switch, not an accident. The dashboard shows
a visible banner whenever it is running in sandbox mode, and every sandbox lease is
tagged `sandbox` in the leases list so it can never be mistaken for a real one.

Three habits keep the production budget intact:

- Do all routine testing in **sandbox mode**. It costs nothing.
- Use the dashboard's **Preview** button. It fills every blank and shows the signers
  without contacting PandaDoc at all, in either mode.
- Run `pytest` for behaviour changes. The suite stubs PandaDoc entirely.

Budget **one** real production document for step 7, addressed to yourself, to prove
the whole path end to end. Do not repeat it once it passes. At roughly five leases a
month the allowance runs out in a year, so if the portfolio grows, the paid plan is
the answer rather than reusing documents.

## 2. Get API keys

1. Open the **Developer Dashboard** (profile menu → *Developers*, or
   <https://app.pandadoc.com/a/#/developers>).
2. Go to **API keys**. Create a **sandbox** key and a **production** key — PandaDoc
   issues both from the same page once sandbox access is enabled on the account.
3. Copy them into `.env`:

   ```ini
   PANDADOC_MODE=sandbox
   PANDADOC_SANDBOX_API_KEY=your-sandbox-key-here
   PANDADOC_API_KEY=your-production-key-here
   ```

Each key is a bearer credential for that half of the account. Both go in `.env`,
which is gitignored. Do not commit either, and do not paste them into the browser —
this app never sends a key to the client.

## 3. Build the lease template

1. Run `python pandadoc/generate_template_body.py` to make sure
   [`lease_template_body.md`](lease_template_body.md) reflects the current
   [`documents/lease.md`](../documents/lease.md) — it's a generated file, never
   hand-edited, so this is always safe and fast to re-run.
2. **Templates → New template → Start from scratch.**
3. Name it something like `Residential Lease` — not "LGD" specifically, since the landlord is chosen per-lease at generation time, not baked into the template.
4. Paste the body from `lease_template_body.md`. Its own header lists the current
   token table; its footer has a print-layout checklist (page size, margins,
   fonts, page breaks, per-page initials) to work through once the wording is in —
   none of that can live in a text file, so it's a manual pass in PandaDoc's own
   editor.

### 3a. Roles

Under **Manage → Roles**, create these exactly — the API matches roles by name, and a
mismatch makes document creation fail:

| Role | Who |
| --- | --- |
| `Lessor` | The landlord signing |
| `Lessee` | First approved potential tenant |
| `Lessee2` | Second tenant (optional) |
| `Lessee3` | Third tenant (optional) |

### 3b. Tokens

Tokens are the `[Group.Name]` placeholders already in the pasted text. PandaDoc picks
them up automatically. Confirm under **Manage → Tokens** that all the tokens listed
in `lease_template_body.md`'s own "Tokens" section (right at the top of that
generated file) appear — that table is regenerated from the current lease every
time, so it's the source of truth on which section each token fills, not a copy
here that can go stale (an earlier version of this section did exactly that: it
said `Utilities.Excluded` fills §13, which was true before the §6 SMOKING clause
was added and everything after §5 shifted up by one).

The years are two digits because the lease pre-prints `20__`. The app sends `26` for
2026 — do not add another `20` in the template.

### 3c. Signature fields

Drag a **Signature** field and a **Date** field onto each signature line and assign
them to the matching role. See the table at the end of
[`lease_template_body.md`](lease_template_body.md).

Mark `Lessee2` and `Lessee3` fields **not required**, or a one-tenant lease will never
reach completed status.

### 3d. Page numbers

The printed lease shows **"Page X of Y" at the top and the bottom of every
page**. In `print/lease_print.html` that comes from CSS `@page` margin boxes,
but a PandaDoc document is not rendered by a browser and takes no CSS from the
template body — so this one has to be switched on by hand, in PandaDoc's own
header/footer settings for the template, to match. Set both a header and a
footer, each centered, in the "Page X of Y" format.

Nothing in this repo can verify that step, so it is easy to lose: if the
template is ever rebuilt from scratch, set it again.

## 4. Get the template UUID

Open the template. The URL looks like:

```text
https://app.pandadoc.com/a/#/templates/ABC123xyz.../content
```

`ABC123xyz...` is the UUID:

```ini
PANDADOC_TEMPLATE_UUID=ABC123xyz...
```

Sandbox and production are separate workspaces, so the sandbox side may need its own
copy of this template with its own UUID:

```ini
PANDADOC_SANDBOX_TEMPLATE_UUID=DEF456uvw...
```

Leave `PANDADOC_SANDBOX_TEMPLATE_UUID` unset and sandbox mode reuses
`PANDADOC_TEMPLATE_UUID` — fine if the two workspaces happen to share templates.

## 5. Set up the webhook

The webhook is what keeps the dashboard's status column current. Without it, leases
stay at "Sent" forever.

1. **Developer Dashboard → Webhooks → Add Webhook.**
2. Endpoint URL: `https://your-domain/webhooks/pandadoc`
   - **HTTPS is required.** For local testing, tunnel with something like
     `cloudflared tunnel --url http://localhost:8000` and use the URL it prints.
     Once actually deployed (see **Deploying** in `README.md`), use the real
     Render URL here instead of a tunnel.
3. Select events: **`document_state_changed`** at minimum. `recipient_completed` is
   useful if you later want per-signer tracking.
4. Copy the **shared key** shown on the webhook. It is what signs the requests:

   ```ini
   PANDADOC_WEBHOOK_SHARED_KEY=the-shared-key
   ```

PandaDoc signs the raw request body with HMAC-SHA256 and passes the hex digest as a
`signature` query parameter. `app/pandadoc.py:verify_webhook_signature` checks it and
the app returns 403 on a mismatch, so an unset or wrong shared key will silently drop
every status update.

PandaDoc retries a failed delivery 3 times and times out after 20 seconds.

Sandbox and production webhooks are configured separately (they live in different
workspaces). Set both up if you want status updates to work in both modes; sandbox
testing works fine without one — the dashboard just won't show status changes for
sandbox leases.

## 6. Set up landlords and logins

Landlords and the people who can log in live in `accounts.json`, not in `.env` —
that file also holds password hashes, so it's gitignored just like `.env`.

```bash
python -m app.accounts init
```

writes a starter file with the two landlords and three users this app was built for:

| User | Role | Can act for |
| --- | --- | --- |
| `kevin` (Kevin Kolb) | admin | every landlord |
| `pam` (Pam Hartnett) | landlord | LGD Properties |
| `gay` (Gay Robertson) | landlord | Orange Street LLC |

Nobody can log in until a password is set for them:

```bash
python -m app.accounts set-password kevin
python -m app.accounts set-password pam
python -m app.accounts set-password gay
```

Each prompts for a password (12+ characters), hashes it with PBKDF2-HMAC-SHA256, and
writes the hash back into `accounts.json`. `python -m app.accounts list` shows who
exists and whether their password is set, without printing any secret.

To add a landlord or user later, edit `accounts.json` directly (or extend
`app/accounts.py`) and run `set-password` for anyone new. A `landlord`-role user's
`landlord_id` must match a landlord's `id` in the same file, or the app refuses to
start with a clear error naming the mismatch.

The landlord's `email` is the `Lessor` recipient on every lease issued under it, so
it must be an address that can receive and act on the signing request.

## 7. Verify

Free checks first — none of these create a document:

```bash
pytest                                                 # stubbed, spends nothing
python -m app.accounts list                            # confirms accounts.json is valid
curl -u pam:PASSWORD http://localhost:8000/api/config   # pam should see only LGD Properties
curl -u kevin:PASSWORD http://localhost:8000/api/config # kevin should see both landlords
```

With `PANDADOC_MODE=sandbox` (the default), open the dashboard and run a lease all
the way through for free: fill the form, **Preview** it, then **Generate lease**, open
the signing link, and sign it. Confirm that:

- every blank in the document is filled, with no stray `[Token.Name]` text,
- the dashboard status flips to **Signed** once you sign (the webhook working),
- the leases list marks the row **Sandbox**,
- the **Download** link on a signed row serves back a PDF.

Only once that whole path works, switch to production for a single real check:

```ini
PANDADOC_MODE=production
```

Address the lease to **your own email**, generate it, and confirm the same four
things. That is 1 of the 60 production documents spent for the year — do not repeat
it once it passes, and switch `PANDADOC_MODE` back to `sandbox` afterward so routine
use doesn't default to spending more.

If a document lands in `document.error`, the cause is almost always a role name or
token name in the template that does not match this repo. Fix the template in
whichever workspace (sandbox or production) you're pointed at before retrying — a
production retry after a template fix still costs another document.
