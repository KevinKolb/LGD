# CLAUDE.md

Project-level context for working in this repo. See [README.md](README.md) for the
full picture (setup, architecture, security). This file covers process notes that
are kept out of the human-facing document files on purpose.

## The lease text lives in two files

- [`originals/lease_transcript_verbatim.md`](originals/lease_transcript_verbatim.md)
  — a character-for-character transcript of the original scanned paper lease.
  Historical record. **Never edit this file.**
- [`originals/lease.md`](originals/lease.md) — the live, editable master. Started
  identical to the verbatim transcript. Edit *this* file when the lease's actual
  wording needs to change. It intentionally carries no process notes or commentary
  of its own, so a human can open and edit it as a clean document — all of that
  lives here instead.

Numbering in the lease originally ran 1–19 continuously across its six pages, with no
section 20 — that was the original scanned document's own numbering, nothing was
missing. A new §6 SMOKING was added on 2026-09-06 (see the changelog below), which
renumbered everything from old §6 onward up by one; the lease now runs 1–20.

## A blank, printable paper lease

[`print/generate_print_lease.py`](print/generate_print_lease.py) is the third thing
derived from `originals/lease.md` (alongside `pandadoc/lease_template_body.md`) — a
self-contained HTML file meant to be opened in any browser and printed
(Ctrl+P / Cmd+P) as a blank paper lease, before any PandaDoc setup exists at all.
Regenerate with:

    python print/generate_print_lease.py

Unlike the PandaDoc generator, blanks stay as literal fill-in lines (there's no
tenant yet to put a token value in) and the four signature lines stay as real
underscore lines too, since this is meant to be signed by hand. The document title's
company branding is a blank line, not "LGD" or any other landlord's name, since the
same print lease is shared across every landlord in `accounts.json` — see
`tests/test_generate_print_lease.py` for what it locks in, including two real bugs
found while building it (signature lines merging into one unreadable blob for the
same underlying reason the PandaDoc generator's paragraph-merge bug happened, and a
context-window that wasn't wide enough to correctly size the Lessor-name blank).

Page numbers ("Page X of Y") use a CSS `@page` margin-box counter — this renders
correctly in Chrome, Edge, and Safari (18.2+), but Firefox does not support it as of
early 2026; printing from Firefox just omits that line rather than showing something
wrong.

## Keeping the PandaDoc template body in sync

[`pandadoc/lease_template_body.md`](pandadoc/lease_template_body.md) is a
**generated file** — never hand-edit it. It's produced from `originals/lease.md`
by [`pandadoc/generate_template_body.py`](pandadoc/generate_template_body.py):
same wording, with each blank replaced by a PandaDoc token (`[Group.Name]` form).
It's what actually gets pasted into the PandaDoc template editor.

**Whenever `originals/lease.md` changes, run the generator and re-paste the
result into PandaDoc:**

    python pandadoc/generate_template_body.py

There is still no *automated* sync into PandaDoc itself — that paste is a manual
step — but the two local files can no longer silently drift apart, since the
second one is machine-derived from the first. The generator fails loudly (raises,
doesn't guess) if a blank has moved, been removed, or a new one appeared that it
doesn't know about — see `tests/test_generate_template_body.py` for what it
guards against, including a real bug it was built to fix: the scanned lease's
page cuts sometimes fall mid-sentence, and a naive "blank line = new paragraph"
approach silently mangled those sentences on the first attempt.

Blank fill-in lines (`__________`) in `originals/lease.md` are filled per-lease by
the app via PandaDoc tokens at send time, not by editing the file directly — see
[`app/lease.py`](app/lease.py) for the token mapping used at runtime (a separate,
hand-maintained mapping from the generator's — keep both in mind if a blank is
ever added or removed).

## Wording is a legal decision, not a typo to autocorrect

The original scanned lease has several apparent OCR-era wording quirks. Never "fix"
one on your own initiative — if it's in the executed paper lease, changing it changes
the instrument. That's a decision for whoever has legal authority over the document
(the user), made deliberately, not something to autocorrect in passing.

Eight were reviewed and corrected by the user on 2026-09-06, in both
`originals/lease.md` and `pandadoc/lease_template_body.md`. Section numbers below are
**current** (post-2026-09-06 renumbering, see the changelog after this table):

| Section | Before | After |
| --- | --- | --- |
| §2 | "revoke of eviction notice" | "revocation of the eviction notice" |
| §3 | "failure to full and faithfully perform" | "failure to fully and faithfully perform" |
| §9 | "proceedings be commended by or against" | "proceedings be commenced by or against" |
| §9 | "said premise are occupied" | "said premises are occupied" |
| §13 | "shall not be effected thereby" | "shall not be affected thereby" |
| §10 | "become due and eligible" | "become due and payable" |
| §20 | "a waiver of relinquishment" | "a waiver or relinquishment" |
| §20 (multi-tenant) | "jointly and solidarity liable" | "jointly and solidarily liable" |

`originals/lease_transcript_verbatim.md` still preserves the pre-correction wording,
untouched, as it always will.

If another apparent typo turns up later, flag it and ask — don't fix it silently.

## E-signature provider: on hold, moving off PandaDoc

As of 2026-09-06, the user decided to move off PandaDoc for e-signature (cited its
template editor as "quite the clunker") to some other provider, not yet chosen.
Everything PandaDoc-specific is parked, not removed: `app/pandadoc.py`, the
template/role/token setup in `pandadoc/TEMPLATE_SETUP.md` steps 3-5, and the
`PANDADOC_TEMPLATE_UUID`/`PANDADOC_WEBHOOK_SHARED_KEY` env vars. `.env` has
temporary placeholder values (`placeholder-pending-signature-provider`) for both,
since `Settings.load()` requires them non-empty to boot at all — without a
placeholder the app can't start even to serve the dashboard/login, which have
nothing to do with signing. Replace both with real values (or replumb this app
entirely for the new provider) before "Generate lease" can work; login, the
dashboard, and the blank-lease print button don't depend on this at all.

Everything else already built — the dashboard, accounts, lease DB, archive
storage, the Render+Supabase dual-backend work below — is provider-agnostic and
does not need to change when the provider does. Only `app/pandadoc.py` (the
client), `app/main.py`'s calls into it, the webhook receiver, and the token
mapping in `app/lease.py` are PandaDoc-specific and would need rewriting for a
new provider's API.

## Two storage backends, one call site each

`app/db.py` (leases), `app/config.py` (accounts), and `app/archive_storage.py`
(signed PDFs) each support two backends — local files (SQLite / `accounts.json` /
a local folder) and Supabase-hosted (Postgres / Postgres / Storage bucket) — chosen
purely by what a config string looks like (`DATABASE_URL` set at all, a `db_path`
starting with `postgres://`, an `archive_dir` starting with `supabase:`). This
exists only because Render's free tier — the free, no-credit-card hosting path,
picked for exactly that reason — wipes local disk on every restart; a plain laptop
run or the test suite never sets any of these variables and behaves exactly as
before this existed. See **Deploying** in `README.md` for the actual setup steps.

Every caller (`app/main.py` routes, `app/accounts.py`'s CLI) passes the same
config string through unchanged and never branches on which backend is active —
that branching lives only inside the three modules above. Keep it that way: a new
call site should never need to know or care which backend it's talking to.

The three test files `tests/test_db_postgres.py`, `tests/test_config_postgres.py`,
and `tests/test_archive_storage.py`'s Supabase half all mock the network client
(`asyncpg`/`supabase`) rather than touching a real Postgres or Supabase project, the
same way `FakePandaDoc` stands in for PandaDoc — this is what keeps the suite fast,
free, and runnable offline. If a real integration test against a live Supabase
project is ever wanted, it should be separate and opt-in, not part of the default
`pytest` run.

**Every `asyncpg.connect()`/`create_pool()` call must pass `statement_cache_size=0`.**
Found the hard way on 2026-09-06 once a real Supabase project was wired up: the
Transaction pooler connection string (the one to use for `DATABASE_URL` — see
README's Deploying section, it's the one that supports IPv4) runs in transaction
mode, which does not support asyncpg's server-side prepared-statement cache at
all. Without this, queries fail intermittently/permanently with
`DuplicatePreparedStatementError`. All three call sites (`app/db.py`,
`app/config.py`, `app/accounts.py`) already do this — keep it that way in any
new one.

**`tests/conftest.py` has an autouse fixture (`_no_live_credentials`) that
deletes `DATABASE_URL`/`SUPABASE_URL`/`SUPABASE_KEY` from the environment before
every test.** This is load-bearing, not optional: `app/config.py`'s
`load_dotenv()` reads the developer's real local `.env`, and once that file has
real Supabase credentials in it (as it does after actually deploying — see the
`render-supabase-deployment` memory), any test that didn't explicitly override
those three vars would silently start talking to the live Postgres/Storage
project instead of local SQLite/JSON/disk. This actually happened once during
setup on 2026-09-06 before the fixture was added — tests slowed way down
(real network round trips) and started failing in confusing ways. Never remove
that fixture without replacing it with something equally strict.

## Legal research

[`LEGAL_RESEARCH.md`](LEGAL_RESEARCH.md) records the court cases and websites
consulted while drafting or amending specific clauses (e.g. the §19 attorney's-fees
floor, the §14 utilities-penalty amount), including which sources were actually
read in full versus only seen via a search tool's summary. Append to it, don't
replace it, whenever a clause decision draws on outside research — it's meant to
survive as a reference trail, including for potential litigation.

## Clause changes changelog

Additions, restructuring, and amount changes to lease terms — as opposed to the
wording-error corrections table above. See [`LEGAL_RESEARCH.md`](LEGAL_RESEARCH.md)
for the research behind any entry that cites outside sources.

- **2026-09-06 — §6 SMOKING** (approved "for now," per the user). No prior clause
  covered smoking at all. Indoors-only scope; violation is ipso facto default (no
  §10 five-day cure) rather than an ordinary nuisance violation, given fire/odor
  damage risk; cleaning/repair cost is explicitly tied to the §3 security deposit.
  Inserted right after §5 PETS, renumbering everything from old §6 onward up by one
  (old §6–§19 → new §7–§20). Applied identically to `originals/lease.md` and
  `pandadoc/lease_template_body.md`.

- **2026-09-06 — §14 UTILITIES, per-day penalty $5 → $10** (approved by the user).
  See `LEGAL_RESEARCH.md` for the New Orleans utility-cost research behind the
  figure. Applied identically to `originals/lease.md` and
  `pandadoc/lease_template_body.md`.

- **2026-09-06 — §19 ATTORNEY'S FEES, minimum floor $100 → $500** (approved by
  the user; 25% rate unchanged). See `LEGAL_RESEARCH.md` for the NOMAR-standard
  comparison and Louisiana case law behind keeping 25% but raising the floor.
  Applied identically to `originals/lease.md` and
  `pandadoc/lease_template_body.md`.

- **2026-09-06 — §17 SIGNS AND ACCESS, expanded** (approved by the user). Added
  two new paragraphs: (1) Lessee may not post any sign of any kind, including
  political/campaign/advocacy signs, without Lessor's written consent — Lessor's
  existing sign-posting right is explicitly preserved; (2) a carve-out permitting
  reasonable, temporary seasonal/holiday decorations, tied to §15 (no damage) and
  a 14-day post-holiday removal window, with a Lessor override for any safety
  hazard or nuisance. The original single paragraph and the two new ones are now
  three separate paragraphs under one heading, split by party (Lessor's right /
  Lessee's restriction / Lessee's exception), matching this document's existing
  style of paragraph breaks rather than bullets or sub-numbering. Applied
  identically to `originals/lease.md` and `pandadoc/lease_template_body.md`.

Nothing is currently pending in red in `originals/lease.md` — every drafted
change above has been reviewed and applied to both files.
