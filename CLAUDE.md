# CLAUDE.md

Project-level context for working in this repo. See [README.md](README.md) for the
full picture (setup, architecture, security). This file covers process notes that
are kept out of the human-facing document files on purpose.

## Versions: 1.0 is one company on purpose

**1.0 is Lower Garden District Properties, Inc.** - that exact form, comma
and period, set by the user on 2026-09-28 for everything (it was LLC before,
and briefly "LGD PROPERTIES, INC" on the deposit). Every printed document
takes it from `COMPANY_NAME` in `generate_print_lease.py`; the home, login,
resident, applicant and legal research pages carry it as text. **2.0 is this same site sold to
other property management companies.** The version line at the bottom of the
home page tracks it; "we are at version 1 because we can print a lease" is how
the bar was set.

So hardcoding LGD's name, address or phone into a page is *fine* for now — but
say so when doing it, because every instance is a 2.0 migration. As of
2026-09-08 those are: the printed lease's heading and the hub page heading, the
resident page's contact block, the applicant page's company map, and
"New Orleans" as a default in the `properties` table and throughout the lease
text itself. Since 2026-09-28, also the company name in every printed
document's header (one `COMPANY_NAME`), and LGD's own buildings in
`documents/properties.json` (each file carries a `manager_id`, so 2.0 is one
file per company, or a move into the database).

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

The security deposit agreement follows the same rule. Its scan,
[`documents/originals/security_deposit_original.pdf`](documents/originals/security_deposit_original.pdf),
and its character-for-character transcript,
[`documents/originals/security_deposit_transcript_verbatim.md`](documents/originals/security_deposit_transcript_verbatim.md),
were added on 2026-09-28 and are historical record. **Never edit either.**
It is Steve A. Hartnett's form (his name, 1556 Camp Street address and phone
head page 1), not LGD's.

Its live master is [`documents/security_deposit.md`](documents/security_deposit.md),
started 2026-09-28 as the transcript word for word, minus the letterhead and
title (the generator prints LGD's header in their place). Wording changes go
there, and the same rules as the lease apply: never "fix" wording on your
own initiative, and log every change. Regenerate the printable copy with:

    python documents/print/generate_print_deposit.py

`generate_print_deposit.py` imports the lease generator and reuses its
`render_head` (header, font, page counters) and `render_picker_footer` (the
apartment popup and inlined `properties.json`), so the two documents cannot
drift apart in look or behaviour. The popup fills "As Security Deposit for
___", and picks the version of conditions 6 (walls) and 9 (yard) that
matches the lease's §20 and §17 for the same apartment - `ITEM_OPTIONS` in
the generator, "(A) ... (B) ..." in the text, the same `data-option` tags as
the lease. A build error if either document lacks a version the other has.
Wording changes are logged in
[`documents/security_deposit_history.md`](documents/security_deposit_history.md). It is one of the
three forms ticked in the manager page's step 1 (see "Several documents at
once"). Tests:
`tests/test_generate_print_deposit.py`.

Everything document-related now sits under `documents/`, and the split
inside it is the point: `documents/originals/` is frozen source material —
scans and their verbatim transcripts, never edited (it also holds the
scanned paper application and its transcript); `documents/print/` holds a
generator and its generated output; `documents/` itself holds the live
masters that are edited and that the generators derive from, plus
`lease_history.md`, the record of what has changed in the lease and when. `lease.md` sat
in `originals/` for a while, which invited exactly the wrong instinct about
a file that is meant to be edited.

Numbering in the lease originally ran 1–19 continuously across its six pages, with no
section 20 — that was the original scanned document's own numbering, nothing was
missing. A new §6 SMOKING was added on 2026-09-06 (see the changelog below), which
renumbered everything from old §6 onward up by one; the lease now runs 1–20.
A new §20 PLASTER WALLS was added on 2026-09-28, inserted before PARKING so
that PARKING stays the last section; the lease now runs 1–21.

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

### The font is embedded, and that is load-bearing

The printed lease carries **Gelasio** inline as a base64 data URI
(`documents/print/fonts/Gelasio-Variable.woff2`, SIL OFL, license beside it).
This is not decoration — it is what makes the print device-agnostic.

The document used to ask for Georgia. A device that doesn't have Georgia
substitutes something else, the substitute has different advance widths, so
lines break differently and every page ends somewhere else. Measured with
headless Chrome, per-page character counts went from
`[2838, 2422, 3060, 2923, 3101, 2091]` with Georgia to
`[2777, 3154, 3682, 3140, 3253, 429]` without it — that 429-character last
page is a signature page with almost nothing else on it, which is exactly
what printing from a phone produced. With the font embedded the two renders
match to the character.

Three details that all matter, each with a test in
`tests/test_generate_print_lease.py`:

- **Gelasio is metric-compatible with Georgia**, so embedding it did *not*
  re-paginate the desktop output that was already correct — verified by
  rendering before and after (2838 → 2837 characters on page 1).
- **It is a variable font, declared `font-weight: 400 700`.** A static
  regular would leave each browser to synthesize its own bold, and
  synthesized bold differs per engine — reintroducing the same variance.
- **`font-display: block`, and the auto-print waits on `document.fonts.ready`.**
  `window.print()` on `load` can fire while the page is still in a fallback
  face, which paginates on the wrong widths.

**Numbers use Gelasio's lining figures** (`font-variant-numeric:
lining-nums`, the user, 2026-09-29): by default Gelasio, like Georgia, has
old-style figures, where 0, 1 and 2 are x-height and other digits drop
below the line, so "3,000" read as a big 3 and small zeros. The lining set
is in the embedded font itself, the same widths but a slightly wider zero;
every document printed on the same pages with the same text per page
before and after.

Don't add a font-family anywhere in that generator without putting
`"Gelasio"` first, and don't drop the font file thinking it's an asset the
page merely prefers.

### The signature lines are bound to the sentence they execute

`.execution-block` wraps the "Executed in duplicate at ___" paragraph and the
four signature lines in one `break-inside: avoid` unit, so a page break can
never fall between them and leave a bare signature page. `generate()` raises
if the last body paragraph stops being the execution sentence, rather than
silently binding the wrong thing.

This is deliberately a *relative* constraint rather than a fixed page
position — that is what makes it survive a different paper size, margin or
printer. Verified with headless Chrome across Letter and A4 at six margin
settings: 12 of 12 keep them together at 6 pages.

§21 PARKING is the one section with two real, mutually exclusive radio
buttons instead of fill-in blanks: `mark_parking_radios` in the generator
recognizes the two literal sentences "( ) Parking not available at this
address." and "( ) Parking spaces are limited to..." in
`documents/lease.md`, and swaps each for a real `<input type="radio"
name="parking">` inside its own `<label class="checkbox-line">`. On a
blank lease, JS toggles a `.struck` (CSS `text-decoration: line-through`)
class on whichever label's radio is *not* checked. For a chosen address,
the popup sets it and hides the other (see below).

### The apartment picker, and sections that vary by address

[`documents/properties.json`](documents/properties.json) is the table of
apartments: one entry per building, with its `units` (an empty list for a
single house) and its `lease_options`. The generator validates it and
inlines it into the lease page - inlined, like the font, so the page stays
one file that works offline and from `file://`. **Regenerate the lease after
editing it**, exactly as after editing `lease.md`.

Opening the lease - View or Print - first shows an opaque popup (screen
only, never printed) asking for the address and the unit, with a short
summary of that address's parking, walls and yard beneath (`SUMMARY` in the
script - a new option value needs a line there too). Parking, walls and
yard come from `properties.json` alone - the popup had a parking override,
removed on 2026-09-28 at the user's request. Nothing of the lease shows
until one is picked, and the print dialog only opens after. Picking fills
in the premises blank, bold and underlined, and applies the options.
The button is "Generate document" ("Generate documents" for several). There
is no longer a "Leave it blank" button (removed 2026-09-29 by the user), so
a document is always generated for an apartment; the code for a blank form
(version labels, hand-ticked parking radios) is still there, unreached.

**The popup fills the office's blanks** (the user went through every blank
on 2026-09-29). `QUESTIONS` in the lease generator is every question, in
order - lessee name(s), occupants, lease start date, term, monthly rent,
security deposit, holding deposit, signing date - each optional; each
document names the ones it uses (`LEASE_QUESTIONS`, and `QUESTIONS` in the
deposit and application generators), and the combined page asks the
union, each once. Answers fill every blank tagged `data-fill="<key>"`, in
every document on the page. Some keys are worked out rather than asked
(`fillValues` in the script): the Lessor is always `COMPANY_NAME`, the
city it is executed at is the property's `city` or "New Orleans" (a 2.0
migration), net rent is rent less the $50 deduction, the deposit is also
written out ("One thousand two hundred and 00/100") on the deposit form,
and the lease ends on the last day of the month before start + term. The
signing date fills both the lease's "this ___ day of ___" and the
deposit form's "Received ... on ___". Dates start blank; a Today switch
fills in today's date, still editable. The deposit follows the rent and
the occupants follow the lessees until typed over (`FOLLOWS`).

Blanks are tagged **by position** in the lease and deposit (`LEASE_FILLS`,
`DEPOSIT_FILLS`, via `tag_blanks`, which fails the build if the count
changes - a blank added to a master would otherwise shift every tag after
it), and by the label before them in the application (`OFFICE_FIELDS`).
Left for the pen: signatures, the occupants' second line, the
application's applicant fields and "Desired date of occupancy". Page
counts at every address were unchanged, with the questions empty and
with every one answered.

**Viewing is paper, and everything is one tab** (set by the user on
2026-09-29: "everything will be on standard paper"). On screen each
document sits on a `.sheet` - 8.5in wide with the print margins, so every
line breaks exactly where it will on paper - and `fitSheets()` zooms the
sheet down to fit a phone rather than reflowing it. In print the sheet is
`display: contents` and `zoom: 1 !important`, so it adds nothing to the
printed layout: every printed page was compared before and after, blank
and filled, at desktop and phone widths, and none changed.

The manager page opens every document (and the legal pages) in the same
tab and has no Print buttons. Instead each document floats **Back** and
**Print** (`DOC_BUTTONS` in the lease generator, reused by the others;
the legal pages float Back only). Back uses `history.back()` when this site
opened the page, else goes to the manager page. Print waits on
`document.fonts.ready` like the auto-print, and stays hidden until the
popup closes, so it can never print a lease before its apartment is
picked. `DOC_BUTTONS` also closes the `<main class="sheet">` that
`render_head` opens, which keeps the popup and buttons out of the zoom.

**Every site page has a Home button** (the user, 2026-09-29). `shared/footer.js`,
which every site page loads, floats Home bottom right on every page but the
home page itself; a page with its own floating buttons (the legal pages'
Back) puts them in a `.site-float` group *before* the script tag, and Home
joins it on the left. The documents don't load that script (they are
self-contained files), and **the documents have no Home** (the user,
the same day, after one was added): they float Back and Print only, and
Back returns to the page that opened them. While a document's popup is
open, Back is among its buttons instead of floating over them.

The rule, settled by the user on 2026-09-28: **every lease has the same
sections with the same numbers; only the wording inside §17 PATIO/YARD,
§20 WALLS and §21 PARKING varies by address.** A lease shows only its own
version - the others are hidden, not crossed out (crossing out was the
first design, and was dropped). So leases now differ in length by address;
section numbers are what stays constant.

- `SECTION_OPTIONS` names the three sections by bold title (not number,
  since numbers shift). Each heading is tagged `group=any` and always shows.
- In `lease.md`, "(A) ", "(B) " begins a version, which runs until the next
  letter or the end of the section - so a version can be many paragraphs
  and bullets (walls B is). `paragraph_options` tags them; `mark_versions`
  wraps the "(A) " labels, which show only on a blank lease.
- PARKING's two versions are its radio sentences instead
  (`mark_parking_radios`); for a chosen address the radio is hidden and
  the applicable sentence reads as plain text.
- Every property must set all three groups to a value in `OPTION_GROUPS`
  (`"none"` is gone), and every value there must be tagged in the lease -
  both are build errors.

As of 2026-09-28: parking is "limited" only at 1364 Camp, "not-available"
everywhere else; walls are "B" (plaster) only at 1523 St. Andrew, "A"
(standard: no stickers, scratches or holes beyond small nail holes, no
adhesives) everywhere else; yard "A" (Lessee maintains patio/yard and
alley) at 1534 and 1536 Camp and 1428 and 1430 Melpomene, "B" (Lessor
maintains all) everywhere else.

### The rental application

Same treatment as the lease and deposit, since 2026-09-28.
[`documents/application.md`](documents/application.md) is the live master
(already reworked from the handwritten notes on the annotated scan: no
application fee, a holding deposit, plain-language arbitration).
`documents/print/generate_print_application.py` builds
`application_print.html` with the shared header, font and apartment popup,
which fills "Address of property". A short block with blanks is a **row of
fields**: a full-width flex row, 3/8in tall, whose blanks stretch to the right
margin and share the leftover width in proportion to their underscore counts
in `application.md` - so the form's layout is still edited there, by the
relative length of each blank. A long block with a blank (the holding
deposit's "$____") stays prose with an inline blank (`ROW_MAX_TEXT`).
Ticked in the manager page's step 1. Changes are logged in
[`documents/application_history.md`](documents/application_history.md).

- A block beginning `(parking=limited)` in `application.md` is tagged like
  the lease's versions and shows only where that option applies - the
  vehicles section, for addresses with parking.
- `OFFICE_FIELDS` (rent, term, deposit) become optional boxes in the popup
  via `render_picker_footer(..., fields)`, which any document can use; typed
  values fill the blank with that id, empty ones stay blank.
- **Money** (the user, 2026-09-29): every amount's label on the form ends
  in "$" ("Monthly rental rate $", "Security deposit $", "Monthly rent $",
  "Monthly salary $"). `MONEY_FIELDS` marks the popup boxes for amounts
  (`render_picker_footer(..., money=)`): they start as "$", accept only
  digits, "$" and ".", and collapse any number of "$" into one at the
  front. The "$" is dropped from what fills the form, since the printed
  label already has it; a box left at "$" leaves its blank empty.
- **Deposit defaults to the rent** (the user, 2026-09-29): leaving the rent
  box copies its amount into the deposit box, which stays editable. It
  follows the rent only while it is empty or still holds the amount last
  copied, so a figure typed by hand is never overwritten.
- **Term of lease** (the user, 2026-09-29: "months or years, not both"):
  `TERM_FIELDS` gives it a whole-number box and a months/years select
  (`render_picker_footer(..., terms=)`), filled as "12 months" or "1 year".
- While the popup is open, Back is one of its buttons rather than floating
  (it covered the popup's buttons on a short screen); it floats once the
  popup closes.

Two originals, both never edited: `application_original.pdf` (with the
handwritten edit notes, transcribed in `application_original.ocr`) and
`application_original_clean.pdf` (the same printed form without them - its
printed text is what that `.ocr` transcribes).

### The Plaster Walls Addendum

[`documents/print/generate_print_addendum.py`](documents/print/generate_print_addendum.py)
builds `plaster_walls_addendum_print.html`, for a lease at 1523 St. Andrew
signed before §20 WALLS existed (added 2026-09-28). Its rules are **read out
of `lease.md`** - §20 WALLS, version (B), found by title - never copied, so
it and the lease cannot disagree. **Regenerate it after any `lease.md` edit**,
alongside the lease. The premises come from the one `properties.json` entry
with walls "B" (it raises if there are zero or several). Its own wording is
only the opening "made part of and incorporated into..." paragraph and the
closing acknowledgement, in the generator. Signature and date lines for the
Lessor/Agent and three Lessees. On the manager page it sits at the bottom,
unnumbered, under "No longer in use" (moved from step 2c on 2026-09-29).

### Several documents at once

[`documents/print/generate_print_packet.py`](documents/print/generate_print_packet.py)
builds `documents_print.html`: the application, lease and security deposit
on one page, each from its own generator's `render_body` - never copied, so
it cannot drift from the single pages. The popup gains a checkbox per
document (`?docs=lease,deposit` pre-ticks them) and asks each question once:
the address and unit for all, the application's `OFFICE_FIELDS` only while
it is ticked (`data-for-docs`). Unticked documents are hidden.

**This is how every form opens from the manager page** (settled 2026-09-29,
when the user asked for the clearest way to do several documents and for
steps numbered 1, 2, ... with no letters). Step 1, Paper Documents
Generator (renamed from "Documents" the same day), is one
checkbox per form and one "Make documents" button (the user's wording, greyed
out until a form is ticked, then "Make lease" for one, "Make 2 documents"
for more); one form or several, it opens this
page as `documents_print.html?docs=lease,deposit#view`. Since the manager
page already chose, the popup hides its own checkboxes and asks only
"Which apartment are the lease and security deposit for?". A form alone
prints exactly as its own page does (checked at every address), so the
single-document pages are no longer linked from the manager page; they
stay as files, and `app/main.py` still serves the lease one. Step 2 is
Legal. **Regenerate it after editing any of the three masters or
`properties.json`**, alongside that document's own page. The addendum is
left out: no longer in use, and it names a fixed address.

Two things that are load-bearing:

- **In print, `section.document` is `display: contents`** (on screen each
  is its own sheet). Wrapped in a real box, Chrome paginated the lease
  differently from its own page. With no box,
  every document prints exactly as on its own page - checked for each
  document at every address. The break before each later document sits on
  its `h1.company` instead. The one known difference: at 1364 Camp the
  lease fills 6 pages when another document follows it, against 7 on its
  own, with the signatures still kept together. A spacer to force 7 put an
  empty page into the printout instead, so it was dropped.
- **Premises blanks become `data-premises`**, since an id may appear once
  per page; the picker fills `#premises, [data-premises]`. The generator
  fails the build on any other id repeated across documents.

Printed together, "Page X of Y" counts the whole printout: Chrome can give
each document its own header (named pages), but it cannot restart the page
counter.

`HTML_FOOTER` is an ordinary Python string, so a `\"` in its JavaScript
loses its backslash and breaks the entire script - it did, once, while the
picker was being built. `test_the_page_script_parses` runs every script
through `node --check` when node is installed.

## Wording is a legal decision, not a typo to autocorrect

The original scanned lease has several apparent OCR-era wording quirks. Never "fix"
one on your own initiative — if it's in the executed paper lease, changing it changes
the instrument. That's a decision for whoever has legal authority over the document
(the user), made deliberately, not something to autocorrect in passing.

The eight that were reviewed and corrected on 2026-09-06, with the exact
before/after wording, are recorded in
[`documents/lease_history.md`](documents/lease_history.md).
`documents/originals/lease_transcript_verbatim.md` still preserves the
pre-correction wording, untouched, as it always will.

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

The manager page links to it from step 2, Legal (beside the legal checklist), and it is read there as an ordinary
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

Every addition, restructuring and amount change to the lease's terms lives in
[`documents/lease_history.md`](documents/lease_history.md), alongside the
wording corrections above - it is a record of what was done and when, read
occasionally rather than needed on every task, so it sits next to the document
it describes rather than in here.

**Append to it whenever a clause changes**, and to
[`manager/LEGAL_RESEARCH.md`](manager/LEGAL_RESEARCH.md) for the research
behind any change that draws on outside sources. Don't edit entries already
written: they record what was actually done at the time, including references
to files that have since been removed.
