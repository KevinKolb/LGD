# CLAUDE.md

Project-level context for working in this repo. See [README.md](README.md) for the
full picture (setup, architecture, security). This file covers process notes that
are kept out of the human-facing document files on purpose.

## Versions: 1.0 is one company on purpose

**1.0 is Lower Garden District Properties LLC. 2.0 is this same site sold to
other property management companies.** The version line at the bottom of the
home page tracks it; "we are at version 1 because we can print a lease" is how
the bar was set.

So hardcoding LGD's name, address or phone into a page is *fine* for now — but
say so when doing it, because every instance is a 2.0 migration. As of
2026-09-08 those are: the printed lease's heading and the hub page heading, the
resident page's contact block, the applicant page's company map, and
"New Orleans" as a default in the `properties` table and throughout the lease
text itself.

The multi-company scaffolding that already exists should **not** be torn out to
simplify 1.0: `accounts.json` (and its Postgres equivalent) already hold a
`landlords` table with two companies, every record table carries a
`landlord_id`, and the API already scopes a manager to their own company
server-side. That is the spine 2.0 grows from.

## The lease text lives in two files

- [`originals/lease_transcript_verbatim.md`](originals/lease_transcript_verbatim.md)
  — a character-for-character transcript of the original scanned paper lease.
  Historical record. **Never edit this file.**
- [`documents/lease.md`](documents/lease.md) — the live, editable master. Started
  identical to the verbatim transcript. Edit *this* file when the lease's actual
  wording needs to change. It intentionally carries no process notes or commentary
  of its own, so a human can open and edit it as a clean document — all of that
  lives here instead.

The two folders mean different things, and the split is the point:
`originals/` is frozen source material — scans and their verbatim
transcripts, never edited (it also holds the scanned paper application and
its transcript). `documents/` holds the live masters that are edited and
that the generators derive from. `lease.md` sat in `originals/` for a
while, which invited exactly the wrong instinct about a file that is meant
to be edited.

Numbering in the lease originally ran 1–19 continuously across its six pages, with no
section 20 — that was the original scanned document's own numbering, nothing was
missing. A new §6 SMOKING was added on 2026-09-06 (see the changelog below), which
renumbered everything from old §6 onward up by one; the lease now runs 1–20.

## A blank, printable paper lease

[`print/generate_print_lease.py`](print/generate_print_lease.py) derives a
self-contained HTML file from `documents/lease.md`, meant to be opened in any
browser and printed (Ctrl+P / Cmd+P) as a blank paper lease. Regenerate with:

    python print/generate_print_lease.py

Blanks stay as literal fill-in lines and the four signature lines stay as real
underscore lines, since this is meant to be filled in and signed by hand. The document title's
company branding is a blank line, not "LGD" or any other landlord's name, since the
same print lease is shared across every landlord in `accounts.json` — see
`tests/test_generate_print_lease.py` for what it locks in, including two real bugs
found while building it (signature lines merging into one unreadable blob for the
the same underlying paragraph-merge cause, and a
context-window that wasn't wide enough to correctly size the Lessor-name blank).

Page numbers ("Page X of Y") appear at both the top and the bottom of every
page, via `@top-center` and `@bottom-center` CSS `@page` margin boxes — this renders
correctly in Chrome, Edge, and Safari (18.2+), but Firefox does not support it as of
early 2026; printing from Firefox just omits that line rather than showing something
wrong.

§20 PARKING is the one section with two real, mutually exclusive radio
buttons instead of fill-in blanks: `mark_parking_radios` in the generator
recognizes the two literal sentences "( ) Parking not available at this
address." and "( ) Parking spaces are limited to..." in
`documents/lease.md`, and swaps each for a real `<input type="radio"
name="parking">` inside its own `<label class="checkbox-line">`. JS toggles
a `.struck` (CSS `text-decoration: line-through`) class on whichever
label's radio is *not* checked - the chosen option stays plain, the other
is crossed out. Auto-print still fires on page load - picking one first
means cancelling that dialog once, then printing again manually.

## Wording is a legal decision, not a typo to autocorrect

The original scanned lease has several apparent OCR-era wording quirks. Never "fix"
one on your own initiative — if it's in the executed paper lease, changing it changes
the instrument. That's a decision for whoever has legal authority over the document
(the user), made deliberately, not something to autocorrect in passing.

Eight were reviewed and corrected by the user on 2026-09-06, in both
`documents/lease.md`. Section numbers below are
**current** (post-2026-09-07 PARKING move, see the changelog after this table):

| Section | Before | After |
| --- | --- | --- |
| §2 | "revoke of eviction notice" | "revocation of the eviction notice" |
| §3 | "failure to full and faithfully perform" | "failure to fully and faithfully perform" |
| §8 | "proceedings be commended by or against" | "proceedings be commenced by or against" |
| §8 | "said premise are occupied" | "said premises are occupied" |
| §12 | "shall not be effected thereby" | "shall not be affected thereby" |
| §9 | "become due and eligible" | "become due and payable" |
| §19 | "a waiver of relinquishment" | "a waiver or relinquishment" |
| §19 (multi-tenant) | "jointly and solidarity liable" | "jointly and solidarily liable" |

`originals/lease_transcript_verbatim.md` still preserves the pre-correction wording,
untouched, as it always will.

If another apparent typo turns up later, flag it and ask — don't fix it silently.

## `people` and `users` are two different tables, and not yet connected

`people` (in `app/db.py`'s schema) is the directory of everyone the system
knows about — residents, managers, admins and applicants alike, one row each,
with an optional `property_id` because only a resident actually lives
somewhere. It has no read/write code yet; it is schema only.

`users` (in `app/accounts.py`, and mirrored in `accounts.json` locally) is the
**login** table: username, password hash, role, landlord_id. This is what HTTP
Basic auth actually checks, and in production it holds live credentials.

The intent is for `people` to eventually cover logins for all four roles, which
means these two tables describe overlapping humans with no link between them.
**Nothing reconciles them today.** Before wiring anything up, decide which one
owns identity — most likely `people.id` becoming the key and `users` shrinking
to just credentials pointing at it — and treat it as a real migration: the live
`users` table holds real password hashes, and changing how it is read is what
took startup down on 2026-09-07 (see the `users.email` note in `app/config.py`).

Role vocabulary was settled on 2026-09-08: the roles are `admin` / `manager` /
`resident` everywhere — `ROLE_*` in `app/config.py`, the strings stored in
`users.role`, and `people.role`. The old `landlord` / `tenant` values are mapped
forward by `normalize_role()` on every load, in both the JSON and Postgres
paths, and `preload_accounts_from_postgres` also rewrites them in place. **Keep
that mapping.** It is not redundant with the UPDATE: the only authentication
this app has is these rows, so a database still holding the old strings — a
migration that has not run yet, a restored backup — must still log people in
rather than reject every user at once.

Deliberately *not* renamed, so that names still match what they describe:

- The `landlords` table, the `landlord_id` columns, and the `Landlord`
  dataclass. Landlord here is the company a lease is issued under, not the role
  a person holds, and the dataclass maps one-to-one onto the table row.
- `Lessor` / `Lessee` and `lessor_name` / `lessor_id` — the legal parties named
  in the executed lease and in Louisiana law.
- `notices.tenant_username` and `leases.tenants_json`, which are column names;
  the API fields are kept aligned with the columns they write to.

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
rather than a live service — this is what keeps the suite fast, free, and
runnable offline. If a real integration test against a live Supabase
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

[`manager/LEGAL_RESEARCH.md`](manager/LEGAL_RESEARCH.md) records the court cases and websites
consulted while drafting or amending specific clauses (e.g. the §18 attorney's-fees
floor, the §13 utilities-penalty amount), including which sources were actually
read in full versus only seen via a search tool's summary. Append to it, don't
replace it, whenever a clause decision draws on outside research — it's meant to
survive as a reference trail, including for potential litigation.

## Clause changes changelog

**Entries before 2026-09-08 mention `pandadoc/lease_template_body.md`, which no
longer exists.** PandaDoc was removed that day along with the whole e-signature
path; the file was generated from `documents/lease.md`, so anything an entry
says was "applied identically" to both now lives in `documents/lease.md` alone.
The entries are left as written rather than edited, because they are a record
of what was actually done at the time.

Additions, restructuring, and amount changes to lease terms — as opposed to the
wording-error corrections table above. See [`manager/LEGAL_RESEARCH.md`](manager/LEGAL_RESEARCH.md)
for the research behind any entry that cites outside sources.

- **2026-09-06 — §6 SMOKING** (approved "for now," per the user). No prior clause
  covered smoking at all. Indoors-only scope; violation is ipso facto default (no
  §10 five-day cure) rather than an ordinary nuisance violation, given fire/odor
  damage risk; cleaning/repair cost is explicitly tied to the §3 security deposit.
  Inserted right after §5 PETS, renumbering everything from old §6 onward up by one
  (old §6–§19 → new §7–§20). Applied identically to `documents/lease.md` and
  `pandadoc/lease_template_body.md`.

- **2026-09-06 — §14 UTILITIES, per-day penalty $5 → $10** (approved by the user).
  See `manager/LEGAL_RESEARCH.md` for the New Orleans utility-cost research behind the
  figure. Applied identically to `documents/lease.md` and
  `pandadoc/lease_template_body.md`.

- **2026-09-06 — §19 ATTORNEY'S FEES, minimum floor $100 → $500** (approved by
  the user; 25% rate unchanged). See `manager/LEGAL_RESEARCH.md` for the NOMAR-standard
  comparison and Louisiana case law behind keeping 25% but raising the floor.
  Applied identically to `documents/lease.md` and
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
  identically to `documents/lease.md` and `pandadoc/lease_template_body.md`.

- **2026-09-07 — §7 PARKING moved to the lease's last section (new §20)**
  (per the user's request). Old §7–§20 → new §7–§19 shift down by one to fill
  the gap; PARKING becomes §20, right before the execution sentence. Internal
  cross-references updated too: SMOKING's "Section 10" → "Section 9" (OTHER
  VIOLATIONS AND NUISANCES), SIGNS AND ACCESS's "Section 15" → "Section 14"
  (ADDITIONS OR ALTERATIONS). Also added a checkbox to the section: "[ ]
  Parking not available at this address." - checking it crosses out the
  entire clause. Applied identically to `documents/lease.md`,
  `pandadoc/lease_template_body.md`, and `print/lease_print.html` - see
  "A blank, printable paper lease" and "Keeping the PandaDoc template body
  in sync" above for how the checkbox and its strikethrough behavior
  actually work in each (a real HTML checkbox + CSS for print; a single
  `[Parking.Clause]` token, computed in `app/lease.py`, for PandaDoc).

- **2026-09-07 — §20 PARKING's single checkbox became two radio buttons**
  (per the user's request). Same underlying choice as before (parking
  available vs. not), but now presented as two mutually exclusive options -
  "( ) Parking not available at this address." and "( ) Parking spaces are
  limited to..." - with whichever one isn't chosen struck through, rather
  than only ever striking the "limited" sentence when the single checkbox
  was checked. Applied identically to `documents/lease.md`,
  `pandadoc/lease_template_body.md`, and `print/lease_print.html` - see
  "A blank, printable paper lease" and "Keeping the PandaDoc template body
  in sync" above for the updated mechanics in each.

Nothing is currently pending in red in `documents/lease.md` — every drafted
change above has been reviewed and applied to both files.
