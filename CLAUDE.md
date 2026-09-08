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
`managers` table with two companies, every record table carries a
`manager_id`, and the API already scopes a manager to their own company
server-side. That is the spine 2.0 grows from.

## The lease text lives in two files

- [`documents/originals/lease_transcript_verbatim.md`](documents/originals/lease_transcript_verbatim.md)
  — a character-for-character transcript of the original scanned paper lease.
  Historical record. **Never edit this file.**
- [`documents/lease.md`](documents/lease.md) — the live, editable master. Started
  identical to the verbatim transcript. Edit *this* file when the lease's actual
  wording needs to change. It intentionally carries no process notes or commentary
  of its own, so a human can open and edit it as a clean document — all of that
  lives here instead.

Everything document-related now sits under `documents/`, and the split
inside it is the point: `documents/originals/` is frozen source material —
scans and their verbatim transcripts, never edited (it also holds the
scanned paper application and its transcript); `documents/print/` holds a
generator and its generated output; and `documents/` itself holds the live
masters that are edited and that the generators derive from. `lease.md` sat
in `originals/` for a while, which invited exactly the wrong instinct about
a file that is meant to be edited.

Numbering in the lease originally ran 1–19 continuously across its six pages, with no
section 20 — that was the original scanned document's own numbering, nothing was
missing. A new §6 SMOKING was added on 2026-09-06 (see the changelog below), which
renumbered everything from old §6 onward up by one; the lease now runs 1–20.

## A blank, printable paper lease

[`documents/print/generate_print_lease.py`](documents/print/generate_print_lease.py) derives a
self-contained HTML file from `documents/lease.md`, meant to be opened in any
browser and printed (Ctrl+P / Cmd+P) as a blank paper lease. Regenerate with:

    python documents/print/generate_print_lease.py

Blanks stay as literal fill-in lines and the four signature lines stay as real
underscore lines, since this is meant to be filled in and signed by hand. The document title's
company branding is a blank line, not "LGD" or any other manager's name, since the
same print lease is shared across every manager in `accounts.json` — see
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

`documents/originals/lease_transcript_verbatim.md` still preserves the pre-correction wording,
untouched, as it always will.

If another apparent typo turns up later, flag it and ask — don't fix it silently.

## `people` and `webusers`, and who checks a password

`people` (in `app/db.py`'s schema) is the directory of everyone the system
knows about - residents, managers, admins and applicants alike, one row each,
with an optional `property_id` because only a resident actually lives
somewhere, and an optional `manager_id` for the company they belong to.

`webusers` (in `app/accounts.py`, mirrored in `accounts.json` locally) is the
**login** table, and it is a subset: `webusers.person_id` points at the person a
login belongs to, NOT NULL, so **every login has exactly one person**. The
reverse is deliberately not true and never will be - an applicant who filled
in the form, or a resident who has never signed in, is a person with no login.
That was the open question this file used to record; it is settled now, in
favour of `people` being the superset.

The rule is enforced in the database rather than in code, because there is
more than one way to create a login: a website signup, `python -m
app.accounts`, or somebody typing an INSERT into the Supabase SQL editor. A
BEFORE INSERT trigger on `webusers` creates the person row when one is not
supplied, so all three paths obey it. Locally, where `webusers` lives in a JSON
file that no trigger can watch, `python -m app.accounts link-people` does the
same job and is safe to re-run.

**Two different things can check a password, and either is enough:**

- **Supabase Auth** (`webusers.auth_id` -> `auth.users`) is what the live
  website uses. `login/index.html` and `shared/auth.js` talk to it straight
  from the browser, which is the only kind of login that can work at all on
  GitHub Pages, where there is no server. Supabase holds that password; this
  app never sees it.
- **`webusers.password_hash`** (PBKDF2, `app/auth.py`) is what this app's HTTP
  Basic auth checks. That path is not what the live site uses.

So `app/config.py` requires *one* of the two, never both: a row created by a
website signup has an `auth_id` and an empty hash, and one created by the CLI
has the reverse. Requiring both would lock out whichever was made first. An
empty hash must never authenticate - `app/main.py` verifies against a decoy
hash in that case, so it fails exactly like a wrong password, in the same time.

### Public signups create the `applicant` role

Anyone can create an account from the website. They land as `applicant`: a
real login that can see its own row and nothing else, until an admin promotes
them. Two consequences worth keeping in mind:

- `app/config.py` **must accept** `applicant` as a valid role. A role the
  loader rejects is a role that fails startup for every user at once, the
  moment one stranger signs up - the same shape of outage as the `users.email`
  incident below.
- Anything that gates the dashboard has to be an **allow-list** of roles, not
  "anyone who is not a resident". `require_dashboard_role` in `app/main.py` is
  that allow-list. The old exclusion phrasing would have admitted every new
  signup the day this shipped; `tests/test_auth_links.py` locks it down.

### Row level security is the real gate

The browser holds a Supabase **publishable** key (in `shared/auth.js`) - it is
meant to be public, and carries no privileges of its own. What actually
protects the data is row level security, in
`supabase/migrations/001_auth_people_rls.sql`: every table denies the
anon/authenticated roles by default, and exactly three things are granted
back - read your own `webusers` row, read your own `people` row, edit your own
name and phone. No browser policy can change a `role` or a `manager_id`.

**A new table in `app/db.py` is a data leak until it is added to that
migration's RLS list.** `tests/test_auth_links.py` compares the two and fails
if a table is missing, so that mistake surfaces immediately rather than after
someone reads `applications` - which holds every applicant's name, email and
phone number.

The app's own connection is unaffected by any of this: it connects as
`postgres`, which has BYPASSRLS, so `app/db.py` and `app/config.py` read and
write exactly as before.

The `sb_secret_...` key in `.env` is the opposite of the publishable one - it
bypasses RLS entirely. It must never appear in a file a browser downloads;
there is a test for that too.

### Applying a migration

    python supabase/apply_migrations.py            # apply, then report
    python supabase/apply_migrations.py --report   # report only

Every file in `supabase/migrations/` is written to be idempotent, so
re-running the set is the normal way to bring a drifted database back into
line. Before applying anything to the live project, run it inside a
transaction and roll back - that is how the trigger and all fifteen RLS rules
in 001 were checked against real data without committing a thing.

Role vocabulary was settled on 2026-09-08: the roles are `admin` / `manager` /
`resident` / `applicant` everywhere - `ROLE_*` in `app/config.py`, the strings
stored in `webusers.role`, and `people.role`. The old `landlord` / `tenant` values
are mapped forward by `normalize_role()` on every load, in both the JSON and
Postgres paths, and `preload_accounts_from_postgres` also rewrites them in
place. **Keep that mapping.** It is not redundant with the UPDATE: a database
still holding the old strings - a migration that has not run yet, a restored
backup - must still log people in rather than reject every user at once.

On 2026-09-08 the last of it went too: `landlords` became `managers`, every
`landlord_id` became `manager_id`, and that table's `company` column became
`name`. `users` became `webusers` in the same pass - Supabase already has a
`users` table (`auth.users`, where GoTrue keeps identities), and this one is
joined to it, so two tables one schema apart sharing a name was a trap.

Note the collision this leaves, deliberately: `manager` is both a role a
person holds (`webusers.role = 'manager'`) and the name of the table of
management companies, so a row reads `role='manager'`, `manager_id='lgd'`.
The first is a job, the second is a company. Flagged when the rename was
requested and accepted as-is.

Deliberately *not* renamed, so that names still match what they describe:

- `Lessor` / `Lessee` and `lessor_name` / `lessor_id` - the legal parties named
  in the executed lease and in Louisiana law.
- The Python type is still `User`, not `WebUser`. The rename existed to
  disambiguate from `auth.users`, which has no equivalent in Python.

### Old names in code are data, not vocabulary

Several strings look like the words being renamed but are values sitting in
databases and files that already exist. A find-and-replace over them is a
silent breakage, and this happened **five times** during the 2026-09-08
rename before the tests caught each one:

- `LEGACY_ROLES = {"landlord": ..., "tenant": ...}` in `app/config.py` - the
  role strings a pre-rename database still stores.
- `SUPERSEDED_TABLES`' guard columns in `app/db.py` (`("properties",
  "landlord")`) - the column name that identifies the *old* table shape.
- `OLD_SCHEMA` in `tests/test_db_schema.py`, for the same reason.
- `migrate_keys` in `app/accounts.py` and the fallbacks in
  `_load_accounts` - they read `"landlords"`, `"users"`, `"company"` and
  `"landlord_id"` out of an `accounts.json` written before the rename. That
  file is gitignored and holds real password hashes, so it cannot be migrated
  by editing anything committed.
- The `column_name = 'company'` guard in the migration, which finds the
  column as it actually exists in the live database.

`tests/test_config.py::test_an_accounts_file_written_before_the_renames_still_loads`
is the regression guard.

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

The manager page links to it as step 3a, and it is read there as an ordinary
page on this site — not as a raw file on a code host, which is what the link
used to do. [`manager/legal_research.html`](manager/legal_research.html) is a
**generated file** — never hand-edit it. Regenerate it after every append to
the log:

    python manager/generate_legal_research.py

The converter handles only the constructs the log actually uses and raises on
anything else (a table, a fenced code block, a blockquote) rather than dropping
it silently — so if a regeneration fails, add the construct there deliberately.
See `tests/test_generate_legal_research.py`, including the one real bug it
guards: the log puts a blank line between numbered sources, and treating that
as the end of the list restarted every entry at "1.".

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
  `pandadoc/lease_template_body.md`, and `documents/print/lease_print.html` - see
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
  `pandadoc/lease_template_body.md`, and `documents/print/lease_print.html` - see
  "A blank, printable paper lease" and "Keeping the PandaDoc template body
  in sync" above for the updated mechanics in each.

Nothing is currently pending in red in `documents/lease.md` — every drafted
change above has been reviewed and applied to both files.
