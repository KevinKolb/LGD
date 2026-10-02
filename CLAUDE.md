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
applicant page's company map, and
"New Orleans" as a default in the `properties` table and throughout the lease
text itself. Since 2026-09-28, also the company name in every printed
document's header (one `COMPANY_NAME`), and LGD's own buildings in
`documents/properties.json` (each file carries a `manager_id`, so 2.0 is one
file per company, or a move into the database). Since 2026-09-29, also "LGD PORTAL" (the home page's
title bar and the home-screen name in `shared/manifest.webmanifest`), the
company name at the top of the rent register, and the applicant email's
subject and signature on the manager page.

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
three forms ticked in the manager page's step 3 (see "Several documents at
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
security deposit, holding deposit, lease signing date, deposit received
date - each optional; each
document names the ones it uses (`LEASE_QUESTIONS`, and `QUESTIONS` in the
deposit and application generators), and the combined page asks the
union, each once. Answers fill every blank tagged `data-fill="<key>"`, in
every document on the page. Some keys are worked out rather than asked
(`fillValues` in the script): the Lessor is always `COMPANY_NAME`, the
city it is executed at is the property's `city` or "New Orleans" (a 2.0
migration), net rent is rent less the $50 deduction, the deposit is also
written out ("One thousand two hundred and 00/100") on the deposit form,
and the lease ends on the last day of the month before start + term.
Each document has its own date (the user, 2026-09-30): the lease signing
date (`signed`) fills the lease's "this ___ day of ___", the deposit
received date (`received`) the deposit form's "Received ... on ___", each
shown in the combined popup only while its document is ticked. The deposit
form's "Applicant has deposited herewith the sum of $___" is the security
deposit again (the user, same day), so that form asks no holding deposit;
only the application does. Dates start blank - except the
lease start, which opens at the first of next month (`DATE_DEFAULTS`) - and
a Today switch fills in today's date, still editable; turning it off puts
back the blank or the default. The deposit follows the rent and
the occupants follow the lessees until typed over (`FOLLOWS`).

Blanks are tagged **by position** in the lease and deposit (`LEASE_FILLS`,
`DEPOSIT_FILLS`, via `tag_blanks`, which fails the build if the count
changes - a blank added to a master would otherwise shift every tag after
it), and by the label before them in the application (`OFFICE_FIELDS`).
**Every signature has a Date line beside it, for the pen, never the
popup** (the user, 2026-09-30: "on signature lines don't ask for email
address, will provide date instead. No popup"): `signature_row` in the
lease generator, used by the lease, both deposit-form blocks and the
addendum. (From 2026-09-29 a Lessee's line had an Email beside it
instead.) The application's own name-and-Email pairs are applicant
fields, not signatures, and stay. Page counts at every address were
unchanged by the swap. The row carries
the space above it, not its lines - flex items' margins don't collapse,
and on the lines they pushed the deposit form onto a third page.

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
the legal pages and the rent register float the same two). Back uses `history.back()` when this site
opened the page, else goes to the manager page. Print waits on
`document.fonts.ready` like the auto-print, and stays hidden until the
popup closes, so it can never print a lease before its apartment is
picked. `DOC_BUTTONS` also closes the `<main class="sheet">` that
`render_head` opens, which keeps the popup and buttons out of the zoom.

**Save sits beside every Print button** (the user, 2026-09-30; labelled
"Save PDF" until 2026-10-01) - the
documents, the two legal pages and the rent register. It is
`shared/save-pdf.js`: a short popup says where "Save as PDF" is on this
device (iPhone: Share -> Save to Files; Android: the printer name -> Save
as PDF; a computer: Destination -> Save as PDF), and Continue opens the
same print window as Print. So the PDF is exactly the printed pages -
font, page counters and breaks - which a script library drawing its own
PDF would not be; the page's title (already "Residential Lease - 1534
Camp St." and the like) is the suggested file name. The documents load
nothing, so `DOC_BUTTONS` inlines the file when generating (it is plain
ES5 with no backslashes for that reason, and uses no font of its own,
since every font in a document starts with Gelasio); **regenerate the
documents after editing it**. It shows and hides with Print.

**Send sits on every document** (the user, 2026-10-01: "phone share
sheet for now but will add domain and email service too soon"): Back,
Send, Save, Print. A browser cannot email a file by itself, and the
print window cannot hand its PDF to a script, so Send makes the PDF in
the page - `documents/print/send-pdf.js`, inlined by `DOC_BUTTONS` like
save-pdf.js (ES5, no backslashes, no font of its own), which loads two
vendored libraries (MIT; see `documents/print/vendor/README.md`) only when
pressed: **modern-screenshot** draws each visible document with the
browser's own rendering and the embedded font, at the printed width, and
**jsPDF** puts the pages in the file. In between, `pageCuts` cuts each
picture into Letter pages: as full as a page will go, only between lines
of text, never through anything kept whole (signature rows, the execution
block, rows of fields), each document starting a new page, with the same
"Page X of Y" lines. Checked at 1534 Camp: 6, 8 and 11 pages for the
lease, lease and deposit, and all three - the same as the printout - at
about 450 KB a page. Its pages are pictures, so Print and Save stay the
exact ones. **It was html2pdf.js at first** (the same day), whose
html2canvas redraws text itself: the user found the sent copy's
formatting off - numbers in old-style figures (it ignores
`lining-nums`), underlines through the letters - while Save was fine.
html2canvas's own foreignObject mode lost the embedded font (it fell back
to Times and re-wrapped every line), so it was replaced.
Each document is its own picture, at most 16 million pixels, because an
iPhone refuses a bigger canvas (lease and deposit together would be 19).
The popup says "Making the PDF...", then offers **Share** - a second tap,
because a browser allows a share only straight after one - and the share
sheet's Mail gets the PDF attached; the address is typed in Mail. Where a
browser cannot share a file (most Windows and Linux ones) it offers
**Download** instead. When the site has a domain and an email service,
Send should ask for the address and email the PDF itself.
**No "PDF" on a button or in a popup** (the user, 2026-10-01): they name
the document instead - "Save the lease", "Getting the lease and security
deposit ready..." - from the page's title up to " - " (`documentName`, in
both scripts); the print window's own option is called "the Save option".
**A saved file's name ends in today's date**, "Lease - 1534 Camp St.
20261001": Send names its file so, and Save puts the date on the page's
title while the print window is open (the window suggests the title as
the file name), then puts the title back.
`app/main.py`'s `/documents/print/` route serves non-HTML files with their
own type, so the library loads there too.

**No footer; one header bar** (the user, 2026-10-02: "really just need a
back button in upper right. don't need the footer", then "logout and back
buttons same size", "rename back to home and put it in a better place"
and "make the header better man, cmon"). `shared/home.js` replaced
`shared/footer.js` (deleted, with its CSS; it was briefly `back.js`). It
is loaded just before `</body>` on the applicant, resident, manager and
admin pages and on sign-in - not the home page - and lays the page's own
`<header>` out as one bar: the titles (the company line, small
capitals, above the page title) on the left, then on the right the
client picker, Login/Logout (`shared/account.js`, moved in whenever it
lands) and, last and far right, **Home** (always to the home page) - all
pills of one height. Home is a plain word, no house (the user,
2026-10-02: "lose the icon because its colors are static ... move home
button far right"; it was on the left with the house until then). On a phone the buttons take the top row, one line
even on an iPhone SE, and the titles go beneath. Every site page has it
(the user, 2026-10-02: "give the login page the header too. giva all web
pages the header"): the sign-in page's is titled "Sign In" (it had the
company name centered above its card, and Home floating in a corner);
the home page's has no Home. **Applicant and Resident on the home page
sign in first** (the user, same day: "applicant and resident go straight
to login for now"): they link to `login/?next=applicant/` and
`?next=resident/`; the sign-in page reads `next` relative to the site
root and, already signed in, goes straight there. (The Resident link was
`data-soon`, "Coming soon.", until then.) The paper pages - documents, rent register,
legal pages - keep Back / Save / Print only, as the user set them. Page titles are
"Applicant Portal", "Resident Portal", "Manager Portal", "Admin Portal".
**The pages opened from the Manager Portal - the
two legal pages and the rent register - have no Back in a header**: they
float **Back** and **Print** (`.paper-buttons`), like the documents. The documents (self-contained files) load neither, and **the documents have no Home** (the user,
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
Ticked in the manager page's step 3. Changes are logged in
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
steps numbered 1, 2, ... with no letters). Step 3, Paper Documents
Generator (renamed from "Documents" the same day), is one
checkbox per form and one "Make documents" button (the user's wording, greyed
out until a form is ticked, then "Make lease" for one, "Make 2 documents"
for more); one form or several, it opens this
page as `documents_print.html?docs=lease,deposit#view`. Since the manager
page already chose, the popup hides its own checkboxes and asks only
"Which apartment are the lease and security deposit for?". A form alone
prints exactly as its own page does (checked at every address), so the
single-document pages are no longer linked from the manager page; they
stay as files, and `app/main.py` still serves the lease one. The steps
are now 1 Accept Applications, 2 Applicants, 3 Paper Documents Generator,
4 Resident Entry, 5 Monthly Rent Register, 6 Legal, 7 Reports (see
"The Properties report"). **Regenerate it after editing any of the three masters or
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

## Accept Applications

Step 1 on the manager page (the user, 2026-09-30: "popup shows all
apartments and let's manager choose which ones to enable applications
for"). The section shows which apartments are accepting applications, and
**Choose properties** opens a popup with every apartment from
`documents/properties.json` - one group per building, a checkbox per unit,
"Whole house" for a building with no units. Save replaces the company's
list. Each apartment accepting applications shows as a tag with an ×,
which stops it at once (the user, same day: "must be able to undo
accepting applications. xs on tags?"); unticking it in the popup does the
same.

The list is the `open_apartments` table (`manager_id`, `address`, `unit`,
`opened_at`; one row per apartment accepting, so one not listed is not),
in `app/db.py` and in `supabase/migrations/004_accept_applications.sql`.
004 locks the table itself - 001's loop only covers tables that exist when
it runs, and Supabase grants a new public table to anon and authenticated
by default - so the browser reaches it only through
`list_open_apartments()` and `set_open_apartments(apartments json)`,
SECURITY DEFINER, manager or admin only, always the caller's own company.
An apartment already open keeps its `opened_at` when the list is saved
again. The FastAPI app has the same as `GET`/`PUT /api/open-apartments`.

**The Add applicant popup offers only these apartments** (the user, same
day): only buildings with a unit accepting, and only those units. The
section sends the list to it as an `lgd-open-apartments` event whenever it
loads or is saved. With none accepting, the popup says "No apartments are
available at this time." (the user's wording) and Add applicant is
greyed out. That is the page's choice only - `create_applicant` does not
check the list.

**The applicant page shows Apply only while some property is accepting
applications** (the user, same day); otherwise "No apartments are
available at this time." stands in its place, and Check application
status stays. It asks `accepting_applications()` (in 004, signed out,
yes or no only) or the FastAPI app's `/api/accepting-applications`. Apply
starts hidden so it never flashes; if neither answers it shows, since the
signup's own email-on-file check still holds. **004 must be
applied to the live database** like the others.

## Navigation and access, page by page

Settled on 2026-10-02 (the user: "go through and fix and improve nav on
all pages. fix all access problems. site selector only appears if a login
has more than one site assigned", and "page title and name in header is
always momandpop.com until a client/company is identified (after login)
then momandpop.com is replaced with company/client"). Checked by opening
every page signed out and as an applicant, a resident, a one-site manager
and a two-site admin:

- **The name**: every site page's header carries a `data-client` line -
  the home page's title, the company line above the others' titles - and
  `shared/home.js` puts "momandpop.com" there and in the browser tab
  ("Manager Portal - momandpop.com") until a signed-in login's client is
  known (`list_my_clients`, remembered as `lgd-client` only while signed
  in, forgotten when signed out), then that client's name.
- **Login/Logout** is in the header of the applicant, resident, manager
  and admin pages (`shared/account.js`); sign-in has Home only, and the
  home page shows **Logout only, and only while signed in** (the user,
  2026-10-02: "no login on home page, only logoff if necessary") -
  signing in starts from a role's button.
- **A welcome under every page's title** (the user, same day: "generic
  welcome message under page title, personalized if login"): "Welcome."
  signed out, "Welcome back, Kevin (manager, resident)." signed in (the
  first word of the name on file, then the roles held, an admin reading
  as manager; just "Welcome back (manager)." while the name is still an
  email). The role is said only there (the user, same day: "Signed in as
  Kevin Kolb (manager). is duplicative") - the admin page no longer opens
  on a "Signed in as" line.
  `shared/home.js` writes it - into the manager page's `#whoami`, which no
  longer greets on its own. **No pop on load** (the user, same day: "set
  border height to hold space for incoming text"): the line always holds
  its height, the last welcome is kept as `lgd-welcome` (forgotten with
  `lgd-client` when signed out) and shown at once, and Login/Logout starts
  as the right word from the stored session. Measured: the header no
  longer changes height after the first paint, except the very first
  visit signed in, before the client and welcome are known.
- **The site picker** shows on every page for a login linked to more
  than one client (the user, 2026-10-02: "managers with multiple
  companies should be able to change companies from any page"; until
  then only the manager and admin headers, marked `data-client-picker`,
  which is now unused). Header pages get it from `shared/home.js` (on a
  phone the home page's title then goes beneath the buttons); the paper
  pages - Properties report, rent register, rent ledger, both legal
  pages - from `shared/client-picker.js`, first among the floating
  buttons, hidden in print. A ledger of one apartment switches to the
  ledger list (`<body data-after-switch>`). The printed documents have
  none: their popup reads the company remembered in `lgd-client`.
- **Home always shows Applicant, Resident and Manager** (the user,
  2026-10-02: "available on home page always regardless of logged in or
  not"; for a few hours that day, signed in, it showed only the roles
  held). Applicant and Resident go through sign-in, which sends someone
  already signed in straight on.
- **Manager page**: its header (Home, Logout) shows from the start; a
  login without the role gets the refusal under it, never a bare page.
- **Applicant page**: Apply (which makes an account) only while signed out.
- **The legal checklist and research log** were open to anyone: now
  `shared/staff-gate.js` (after `auth.js`, in the head) hides the page
  until a manager or admin is confirmed - signed out, to sign in and back;
  otherwise "This page is for managers." with Home.
- **The printed documents** on the website send a visitor with no stored
  login to sign in and back (a check in `DOC_BUTTONS`; opened as a file,
  or served by the FastAPI app, nothing changes). The rent register and
  admin page already turned non-staff away.

## Clients: a login may work for several companies

The user, 2026-10-02: "make site available to different clients. logins
will be linked to clients ... logins can be linked to more than client."
A **client** is a row of `managers` (the companies): 'lgd', "LGD (Lower
Garden District Properties), Inc." (renamed from "Lower Garden District
Properties, Inc." the same day, everywhere, `COMPANY_NAME` included), and
'robertson', "Orange Street, Inc." (that id is the starter accounts', kept
as data). `supabase/migrations/008_clients.sql` adds `person_clients`
(`person_id`, `manager_id`; locked to the browser), linking a person to
every client they work for, and **`people.manager_id` becomes the client
they are working in now** - so every function since 002, which scopes to
`caller.manager_id`, follows it unchanged. A trigger links anyone filed
under a client (an applicant or resident added in it). `list_my_clients()`
and `set_current_client(client)` (only one the caller is linked to) are
for signed-in callers. 008 also makes `list_applicants` and
`list_residents` (and so the rent register) show **only the current
client's, an admin's too** - an admin switches client to see another's.
Editing rights are unchanged.

`shared/home.js` shows the client picker in the header of the staff pages
(those with Login/Logout) when a login has more than one client, short
names ("LGD", "Orange Street"); switching calls `set_current_client` and
reloads. The current client's name fills any `.company[data-client]` (the
manager page's company line) and is kept in this browser as `lgd-client`,
which the rent register's heading reads.

**Buildings belong to a client** (the user, same day: "put in 123 Canal
St. for Orange for now"): every entry in `documents/properties.json`
carries its own `manager_id` (the file-wide one is gone; a build error if
missing) - LGD's buildings 'lgd', 123 Canal St. (a single house, parking
not available, walls A, yard B) 'robertson'. Every list shows only the
current client's: the manager page's three (`clientProperties`, from the
login's `manager_id`), the rent register, and the documents' popup, which
reads `lgd-client` (`COMPANY_ID`, 'lgd', when none is remembered). For a
client other than LGD the documents also put its name in the heading, the
"Page X of Y" lines (an added `@page` rule) and the Lessor blank; LGD's
print exactly as before. The lease and deposit **text** is still LGD's -
rent paid at 1556 Camp Street, for one. The FastAPI app has no clients - one `manager_id` per login, as
before. Linking a person to a second client is a SQL update of
`people.clients` for now (`update people set clients = clients ||
'robertson' where ...`; the user's own link was given to him as a
snippet, not committed: this repository is public).

**Everyone is in one table, `people`** (the user, same day: "combine all
supabase people related tables into one table. logins. applicants.
residents. managers. previous admins ... designate their role or roles in
the table"). It already held everyone with the login as columns and the
four `is_*` role columns; `supabase/migrations/012_one_people_table.sql`
folds 008's `person_clients` into `people.clients` (a `text[]` of
company ids; a before-trigger adds `manager_id` to it) and drops that
table, and adds `roles`, a generated column spelling the four out
("admin, manager, resident") for reading the table in the dashboard - it
is worked out by the database, never written. `managers` stays: it is the
companies, not people - the user took it for a list of manager people
that was missing him. The other tables (`properties`, `open_apartments`,
`rent_payments`, `news`, `site_settings`, `applications` - the shelved
online form's submissions) are not people. 008 still creates
`person_clients` when the whole set is re-run; 012, after it, folds it
back in.

**Each company's contact details are in the company table** (the user,
2026-10-02: "resident page gets separate contact info blocks based on
company. pull from single company table. edit company table with current
lgd info, all fields"). `supabase/migrations/014_company_contact.sql`
gives `managers` `contact_name`, `phone`, `phone_note`, `website` and
`address` beside `name`, `signer_name` and `email`, and fills in LGD's:
Pam and Steve Hartnett, 504.913.1556 (call or text),
LGD@neworleans.properties, https://neworleans.properties, the office at
1556 Camp St. (where the lease has rent paid), and Steve A. Hartnett as
signer (his name heads the deposit form). Orange Street's are empty.
`get_my_company()` (any signed-in person, their current company) feeds the
resident page's Contact block, which was LGD's written into the page;
signed out it says to sign in. The FastAPI app does not have these
columns or the function.

## The Admin Portal

`admin/index.html`, titled and headed "Admin Portal" (the user,
2026-09-30; it was "Admin reference"), like the Manager Portal.

**Manager and admin are one credential** (the user, 2026-10-02: "let's
combine manager and admin into one credential. pam and kevin are
managers. current admin page is accessible through a gear button on
manager page"). The admin page lets in a manager (or an admin) and is
reached from the **gear** in the manager page's header (`data-gear`,
beside Logout); its own header has **Back** to the Manager Portal in place
of Home (`data-up`). The home page has no Admin button. On a phone, when
the header carries the site picker, the gear, Logout and Back, the
picker narrows and the gaps shrink so they all fit one row (`crowded`).
`supabase/migrations/009_managers_are_admins.sql` makes every admin a
manager and lets any manager set the site colors; the FastAPI app's admin
endpoints use `is_staff` (manager or admin). The `is_admin` column stays,
unused by the pages - an admin keeps 002/007's power to edit another
company's records. Site colors are site-wide, so a manager of any client
changes them for every client.

## Site colors

The admin page's **Site colors** section (the user, 2026-09-30: "change the
sites two main colors") sets the two colors every site page is built on:
`--accent`, the main color (Tulane green: header bars, buttons, links),
and `--accent2`, the second (Tulane light blue: the line under each
header, hovers, the home page's Manager and Admin buttons). A color picker
and a `#rrggbb` box each, a live preview, **Save colors**, and **Back to
Tulane green and blue**, which clears them.

**Each company has its own pair** (the user, 2026-10-02: "separate
colors by company, settings only apply to current company"). On Supabase
they are `managers.accent` / `accent2` (`supabase/migrations/010`; 005 kept
one site-wide pair in `site_settings`, which 010 gave to LGD and cleared):
`get_site_colors()` answers with the caller's current client's (both null
signed out), and `set_site_colors(accent, accent2)` - any manager since
009 - saves only the current client's. The section on the admin page is
titled "Colors for <company>". The FastAPI app keeps them as
`site_settings` rows "accent:<company>" / "accent2:<company>", and its
`GET /api/site-colors` now needs a login (pages are gray signed out
anyway); `PUT` is a manager's, for their own company.

`shared/theme.js` puts them on the page, asking as the signed-in person
(the stored session's token) and remembering them per client
(`lgd-site-colors:<client>`), so switching company switches colors. It is loaded in the `<head>` of
the six site pages (home, applicant, resident, manager, admin, login -
not the printed documents or the rent register, which print in their own
colors). **Signed out, every page is black, white and gray** (the user,
2026-10-02: "black white and gray on home page no login. enable colors
site wide when user logs in"): with no session stored (`lgd-auth`),
theme.js sets `GRAYS` - near-black main, light gray second - and asks for
nothing more; signed in, the colors are the admin's, or each page's own
Tulane green and blue. (Earlier the same day the home page was locked to
Tulane colors, and its `?org=o` orange scheme removed.) It sets the variables on `<html>` itself so they outrank each page's
stylesheet and the `?org=o` orange scheme, and keeps the last colors in
localStorage so a page never flashes the old ones before it has asked
again. With none saved it sets nothing and every page keeps its own.
The text on the main color is worked out from it (white, or dark ink on a
light color); the second color always carries dark ink, so the admin
section warns when a dark one is picked. `theme.js` holds a copy of
`auth.js`'s Supabase address and publishable key; a test keeps them equal.

**The admin page on GitHub Pages** used to say "Admins only." to everyone,
admins included: it asked the FastAPI app for `/api/admin/info`, got
GitHub's own "page not found", and read every 404 as a refusal. Only the
app answers in JSON, so now only a JSON 404 means "not an admin"; anything
else falls back to Supabase, which lets an admin in to Site colors. And
since the user still saw a blank page (2026-09-30), every way the page can
end now says so in words: signed in as a manager, Site colors (the
"Signed in as" line it opened on is gone; the welcome says the role); as anyone else, who is signed in, their email and roles,
and that the record needs `is_admin`, with a Sign out button; a login with
no `people` row, that it has no record on file yet; any error, the error;
and still "Loading…" after 20 seconds, that the login service did not
answer.

## A manager adds an applicant (the first "less print" feature)

The manager page's step 2, Applicants (2026-09-29; step 1 until Accept
Applications went before it the next day), is three buttons (the user, 2026-09-29): **Add
applicant**, **View current applicants** and **View archived applicants**.
No list shows until one of the View buttons is pressed; pressing it again
hides it.

**A manager approves an applicant with their email address** and the
apartment and unit they may apply for, in a popup (`<dialog>`). Nothing
else: "The applicant will fill in the rest when they create an account"
(the user). It stores a `people` row with `is_applicant` set, in the
manager's own company, with `full_name` holding the email until they sign
up (the column is NOT NULL). Their first and last name and phone arrive
with their signup on the applicant page, in Supabase's user metadata,
which 001's trigger copies onto the row, keeping anything already on file.
Until then the list shows their email and "No account yet". (The first
version, earlier the same day, had the manager type first, last, email and
mobile.) Someone already in `people` with that email (a resident applying
for another apartment) is not a second person: their row becomes an
applicant too. Only an applicant already on the current list is refused.

Once added, the popup offers **Send application** (the user: "When an
applicant is created give the option to send application") beside Done.

Its wording is the user's: "Add a person you approve to apply. They will
be emailed a link to the application." Nothing is sent automatically yet:
Send application opens the manager's own mail with the link.

**The apartment** (the user, same day: "Manager specifies an apartment and
a unit when creating an applicant") is two selects from
`documents/properties.json` - the unit only for a building with units,
both required. It is stored as text in `people.apply_address` /
`people.apply_unit`, written as `properties.json` writes it, and is *not*
`property_id`, which is where a resident lives. The list shows it, the
Application button's popup starts on it, and the email names it. The
FastAPI app serves `/documents/properties.json` (manager/admin only) so the
same relative fetch works on both hosts.

Each current applicant in the list has three buttons (the user, same day):

- **Application** opens `documents_print.html?docs=application&applicant=<id>#view`
  with what is known of the applicant (email, apartment, and their name and
  mobile once they have signed up) in the manager page's
  `sessionStorage` ("lgd-applicant"). The popup says "For Jane Doe." and
  fills the three blanks the application generator tags `data-applicant`
  (`APPLICANT_FIELDS`: the first blank after "Name of Applicant",
  "Telephone #" and "Email" - later Email blanks are the occupants'). It
  fills only when the stored id matches the address, so a document opened
  any other way never gets a stale applicant.
- **Send application** (the same as in the popup) is a `mailto:` with a
  subject, the apartment, and the link to the applicant page, telling them
  to choose Apply and create their account with that address. A mailto
  cannot attach a file; a paper application printed to PDF can be attached
  by hand. Sending from the site itself would need a mail service and a
  server step.
- **Archive** sets `people.archived_at`: off the list, kept in the
  directory. **View archived applicants** lists them, each with
  **Restore**. Adding an archived applicant again restores the same row.

On the live site (GitHub Pages) the browser still cannot write `people` -
001's default deny stands. It calls three SECURITY DEFINER functions from
`supabase/migrations/002_manager_adds_applicants.sql` through
`LGD.auth.rpc()`: `create_applicant`, `list_applicants(archived)` and
`set_applicant_archived(person_id, archived)`. They check the caller is a
signed-in manager or admin, touch only the caller's own company (an admin:
every company), always file a new row under the caller's own `manager_id`
(never one the browser sends), and are granted to `authenticated` only.
Served by the FastAPI app, the page calls `/api/applicants`
(`?archived=true`) and `POST /api/applicants/{id}/archive` instead, with
the same checks and wording in `app/db.py`.

**The login half:** 001's `handle_auth_user_confirmed` gives a new login
to an unclaimed person with the same email (`auth_id is null`), rather than
making a second one. So when the applicant signs up with the address the
manager typed and confirms it, their login is that same row. The manager
page shows "Has a login" / "No login yet". Sending them an invite email is
not built yet: creating an auth account needs Supabase's secret key, which
must never reach a browser, so it needs a server-side step (an Edge
Function, or the FastAPI app).

**001 and 002 must be applied to the live database** (`python
supabase/apply_migrations.py`). Both were checked against a local Postgres
16 with a stand-in `auth` schema, from the old live shape and from an
empty database, each applied twice cleanly: anonymous callers refused, a
signed-in applicant refused, each manager seeing only their company, an
admin seeing all, archive and restore, and a signup with the same email
linking to the manager's record with no duplicate person.

## The monthly rent register

`manager/rent_register.html` (the user, 2026-09-29: "a printable page for
now that lists all units, tenants, email and phones and a place for a
written date it was received"), step 5 on the manager page. One row per
unit from `documents/properties.json` (a house with no units is one row),
so an empty unit still has its row; every tenant of a unit in that row;
and a blank "Date received" column plus a "Month of ____" line, for the
pen. One letter-size portrait sheet holds every unit (checked in headless
Chrome); on a phone the sheet is zoomed down to fit, like the documents.

Tenants are `people` with `is_resident`, matched to a unit through
`property_id` -> `properties` (`address`, `apt`) - the address written as
`properties.json` writes it. Someone living at an address that file does
not have is still listed, at the bottom, not dropped. Data comes from
003's `list_residents()` on GitHub Pages or `/api/residents` from the
FastAPI app; both let in only a manager or admin, scoped to their company
(an admin sees all).

**By month** (the user, 2026-09-30: "choose a month before opening
register ... choose year and month ... mind lease dates if exist when
showing who resident is"). The register opens on a popup asking the month
and year (it starts on `?month=YYYY-MM` if the address has one, else this
month); the heading then reads "Month of September 2026". On screen it is
a sheet of Letter paper (the user, same day: "look like a piece of
paper") - 8.5 x 11 with @page's 0.5in margins, white on grey with a
shadow, zoomed to fit a phone - with only **Back** and **Print** floating
(the user: no Home, no Change month; to change month, go Back and open it
again). So, like the documents, it does not load `shared/footer.js`
(which adds Home to a `.site-float` group) and has no site footer. `supabase/migrations/006` adds:

- `people.lease_start` / `lease_end` ("YYYY-MM-DD", either may be empty).
  `list_residents(month)` (it replaces 003's no-argument one) leaves out a
  resident whose recorded lease covers no day of that month; one with no
  dates always shows. Resident Entry (below) sets them.
- `rent_payments` (`manager_id`, `address`, `unit`, `month`,
  `received_on`, ...), one row per apartment per month, locked to the
  browser; `list_rent_payments(month)` and `set_rent_payment(month,
  address, unit, received_on)` (an empty date takes it off), managers and
  admins, own company only. The FastAPI app has `GET /api/residents?month=`,
  `GET`/`PUT /api/rent-payments`.

On screen each Date received is a date box, saved the moment it changes
(its border turns green, or red with the old date put back on failure).
In print the box is hidden and the recorded date shows as text with the
day of the week ("Thu, Sep 3, 2026", the user, same day), or the cell
stays blank for the pen - still one letter-size sheet. Text in every cell
is left-aligned and vertically centered.

### The rent ledger

The register's second view (the user, 2026-10-02, with a photo of the
paper rent card in the binder - one page per apartment per year: "Secondary
view of rent register should show history. Make a modern version of
attached. Should be a paid checkbox too."). Each apartment on the
register is a link to `manager/rent_ledger.html?address=&unit=&year=&month=`
(month is where Back returns the register to): a Letter sheet like the
register, with the address and unit, a year switcher (‹ 2025 **2026**
2027 ›) for the history, the tenants with their phones and the lease
dates, and a row a month - date received, rent, deposit, **Paid** and
comments - totalled at the foot ("10 of 12 paid", the rent paid, any
deposits). Every change saves as it is made. Ticking Paid fills an empty
date with today and an empty rent with the nearest month's amount, both
still editable.

`supabase/migrations/013_rent_ledger.sql` gives `rent_payments` `amount`,
`deposit`, `paid` and `note` (dates already recorded were ticked Paid
once, when the column was added); a month may now have no date
(`received_on` is then `''`, the column stays NOT NULL like the FastAPI
app's). `save_rent_entry(...)` writes a whole month and takes off a month
with nothing in it; `list_rent_history(address, unit, year)` reads a
year. The register's date box (`set_rent_payment`) now ticks Paid with a
date and takes the tick off when cleared, keeping the month's amount,
deposit and comment. The FastAPI app has `GET /api/rent-history` and
`PUT /api/rent-entries`. Not on the card yet: its Alarm and Pets lines.
The manager page's step 5 links both (the user, same day: "link to both
rent registers on manager's page"): **Rent register** and **Rent
ledgers**, which opens the ledger with no apartment - a list of the
company's apartments, each opening its ledger for this year, whose Back
returns to the list.

### Resident Entry

Step 4 on the manager page, **temporary** (the user, 2026-09-30: "to get
the rent register up and running for 10/1 add a temporary manager section
called resident entry. let there be more than one resident per unit. let
manager provide as little info as they can, all optional ... this will
expand to user accounts at some point"). **Add resident** opens a wide
popup where only the apartment (and its unit, for a building with units)
is required; first and last name, email and phone are optional. Lease
dates are not asked for now (the user, same day) - the database still
holds them, and Edit sends back whatever a resident already has. A
resident with no name shows as their email, or "Resident". **View current
residents** lists those whose lease covers this month, or who have no
lease dates (everyone, for now), each with **Edit** (the same popup,
filled in) and **Remove** (after a confirm).

A resident is an ordinary `people` row - `is_resident`, and `property_id`
pointing at a `properties` row for the apartment, made on first use - so
the rent register needs nothing of its own, several residents of one unit
are just several rows, and one entered with an email is the very row their
login attaches to when they sign up (001's trigger). An email already in
the directory (an applicant) makes that person the resident rather than a
second person. **Remove** only takes them out of the apartment
(`is_resident` off, `property_id` and lease dates cleared); the person
stays. `supabase/migrations/007_resident_entry.sql`: `save_resident(...)`
(with `person_id` to edit) and `remove_resident(person_id)`, managers and
admins, own company only; `list_residents` gains first and last name. The
FastAPI app has `POST /api/residents` and `DELETE /api/residents/{id}`.

The first resident, Kevin Kolb (the user: admin, manager and resident at
1558 Camp St., Unit A), was put there on 2026-09-29 by a SQL snippet given
to him rather than a committed migration - this repository is public, and
it held his phone number - before Resident Entry existed.

## The Properties report

Step 7, Reports, on the manager page; the first report (the user,
2026-10-02: "it's more of a graphic really. it shows each house with each
unit in it with each resident in it. eventually houses will show status
like lease expiring or vacant etc."). `manager/property_report.html`
draws a house per building of the current client's in
`documents/properties.json` - a roof, the address, a box per unit (a
house with no units is one "Whole house" box) and every resident of that
unit, from `list_residents(month)` for this month (or `/api/residents`),
managers and admins only. A summary line counts buildings, units,
residents and vacancies. **Status lives in `unitStatus()`**: so far
Vacant (nobody on file) and "Lease ends ..." (a recorded `lease_end`
within 60 days); add the next one there, with a colour and a legend
entry. A resident at an address or unit the file lacks gets a house of
their own rather than being dropped. Each house shows a Google map of
its address (the user, same day) - the keyless embed,
`google.com/maps?output=embed&z=17&q=...`, in a lazy iframe - and the
address itself opens Google Maps in a new tab. A building may name its
own embed in `properties.json`, `"map_embed"` (a Street View the user
picked; only a `https://www.google.com/maps/embed?` address is used), and
addresses in one building share a `"building"` name ("1534-1536 Camp
St.", "1428-1430 Melpomene St.", "1521-1523 St. Andrew St.", the user,
same day) - the report draws
them as one house, each address a box named by its number ("1534"). The
documents ignore both keys. The user sent Street Views for 1534, 1536,
1428 and 1430; the rest (1364 and 1558 Camp, 1521 St. Andrew) were worked
out the same day ("infer the missing street view embed codes"): the
house's point and its street's line from OpenStreetMap (Nominatim), the
camera on the street nearest the house, aimed at it - the embed takes a
position and heading without a panorama id
(`pb=!6m7!1m6!2m2!1d<lat>!2d<lng>!3f<heading>!4f0!5f...`). Checked against
the user's 1534 one (within a meter, 104° against his 101°) and by eye;
the even side of the 1500 block of Camp faces Coliseum Square, so its
houses are at about 104°. A shared building uses its first address's
embed. **A building's own photo wins over both** (the user, same day: "use
this image instead of embed but link to map"): `"photo":
"shared/photos/<name>.jpg"` in `properties.json` shows that picture instead
- as **the background of the whole house** (the user, same day: "make the
images the background for the house not above text"), with the address on
a light band at the top, a clear strip of photo, and the unit boxes nearly
opaque over the rest; the address still opens Google Maps. Every LGD
building has one now (sent by the user); only 123 Canal St. shows a map.
Unlike a map, a photo prints. **The houses are landscape and plain** (the
user, same day: "make houses more landscape. remove green door. simple
shape"): at least 430px wide (two across on a computer and in print, one
on a phone), a low roof without overhang, no door, and the unit boxes as
many across as fit. Back, Save and Print float like the
rent register's; it prints in colour, three houses across.

**Unit names are as written on paper** (the user, same day: "#2 (102)
for example"): 1364 Camp's units are "#1 (101)" ... "#7 (204)", 1521 St.
Andrew's "#1" ... "#6", 1558 Camp's A, B, C. A unit is stored by its
name everywhere (`properties.apt`, `open_apartments`, `rent_payments`,
`people.apply_unit`), so renaming one in `properties.json` needs a
migration renaming it in those too - `supabase/migrations/011_unit_names.sql`
did this one. The FastAPI app's local SQLite was not migrated. Printed
documents read "1364 Camp St., Unit #2 (102)"; page counts at every
address were unchanged.

## The house icon

The little house (`favicon.ico`, and `shared/icons/house.svg` drawn to
match: Tulane green roof and door `#006747`, blue walls `#418fde`, outline
`#00391e`) is the icon everywhere, the iPhone home screen included
(`apple-touch-icon.png`, on white, since iOS turns transparent corners
black), with 192/512 PNGs and `shared/manifest.webmanifest`. Every page,
the generated documents and legal research included, carries the same
five head lines; `tests/test_icons.py` checks each one. The name on a home
screen is "LGD PORTAL", which is also the home page's title bar (the
user, 2026-09-29).

**The home page has the header bar too, minus Home** (the user,
2026-10-02: "give home page the header minus home button. title on home
page will be momandpop.com for now"): `<header data-no-home>`, titled
"momandpop.com" (the browser tab too; the home-screen name stays "LGD
PORTAL"), with Login/Logout on the right (`shared/account.js`), on one
row even on a phone; no client picker there. The card lost its company
heading and opens on "Choose your role.". (Earlier the same day a Logout
button sat under the card.)

**The home page tells a phone how to add it to the home screen** (the
user, 2026-09-30: "the first time the person goes to the page"): a popup
with three steps, Share -> Add to Home Screen -> Add on an iPhone or iPad,
menu -> Add to Home screen -> Add on Android, and "Got it". Only on a
phone or tablet, never when opened from the home screen already, and once
per browser (`lgd-home-screen-tip` in localStorage, set when shown; if
storage is unavailable it is not shown at all). Tests:
`tests/test_home_screen_tip.py`.

## Saved for later: `_saved/`

Finished work that is not live yet goes in `_saved/`, with a line in its
`README.md`. GitHub Pages builds this site with Jekyll, which does not
publish folders starting with `_`, so nothing there is on the website -
**don't add a `.nojekyll` file**, or it all goes live. First in:
`_saved/applicant_form.html`, the online rental application that was the
applicant page until 2026-09-29, when the user had the page say "Coming
soon" for now; the last commit with it live is `e81c562`. To
restore it, move it back to `applicant/index.html`.

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

## `people` is everyone, logins included, and who checks a password

`people` (in `app/db.py`'s schema) is the directory of everyone the system
knows about - residents, managers, admins and applicants alike, **one row
each**, with an optional `property_id` because only a resident actually
lives somewhere, and an optional `manager_id` for the company they belong to.

**Roles are four yes/no columns, not one value** (the user, 2026-09-29:
"User can be applicant and resident... Can be manager and admin too. All
one table."): `is_applicant`, `is_resident`, `is_manager`, `is_admin`. In
Python a `User` has `roles` (a frozenset), plus `role` - the most senior
one held, in `ROLE_ORDER` (admin, manager, resident, applicant) - and
`role_label` ("admin, manager") for showing. A gate allows a person who
holds *any* allowed role. `shared/auth.js`'s `profile()` returns the same
three. A login with no role column set is an applicant, never a startup
failure.

**A login is columns on the person's row**, not a table of its own:
`username`, `password_hash` and `auth_id`. There was a separate `webusers`
table, with a `person_id` pointing here; 001 merged it into `people` on
2026-09-29 and dropped it, and dropped the old single `role` column after
reading it into the four flags. Until the migration has run on a
database, `app/config.py` reads the old `webusers` table, and
`shared/auth.js` falls back to it, so signing in never waits on a
migration. A person with no login - an applicant a manager added, a
resident who has never signed in - just has those columns empty.

Locally the logins live in `accounts.json`, under the key `"webusers"`
still (it holds real password hashes and is gitignored, so it is never
renamed by editing anything committed), each with a `"roles"` list
(an old `"role"` is read too). `python -m app.accounts link-people` gives
each one a `people` row, and is safe to re-run.

**Two different things can check a password, and either is enough:**

- **Supabase Auth** (`people.auth_id` -> `auth.users`) is what the live
  website uses. `login/index.html` and `shared/auth.js` talk to it straight
  from the browser, which is the only kind of login that can work at all on
  GitHub Pages, where there is no server. Supabase holds that password; this
  app never sees it.
- **`people.password_hash`** (PBKDF2, `app/auth.py`) is what this app's HTTP
  Basic auth checks. That path is not what the live site uses.

So `app/config.py` requires *one* of the two, never both: a row created by a
website signup has an `auth_id` and an empty hash, and one created by the CLI
has the reverse. Requiring both would lock out whichever was made first. An
empty hash must never authenticate - `app/main.py` verifies against a decoy
hash in that case, so it fails exactly like a wrong password, in the same time.

### A login only for an email address on file

Since 2026-09-29 (the user: "make sure that email address exists in user
table already; if not, don't continue ... and say: that email address is
not yet on file") a login is created only for someone already in `people`
- an applicant a manager added, or anyone an admin put there. Three places
hold it:

- The applicant page, which is where a login is created now - enabled on
  the home page on 2026-09-29 (the user: "enable the applicant page"); the
  home page's "Coming soon." box is now only for a link marked
  `data-soon` - just Resident. It opens on
  two buttons only, **Apply** and **Check application status** (the user,
  2026-09-29). Apply asks the email first, checked by
  `LGD.auth.emailOnFile` (003's `email_on_file`, callable signed out,
  answering only true/false); only after a yes does it ask first name,
  last name, phone and a password. Otherwise it says exactly "That email
  address is not yet on file." Check application status works only signed
  in. Each button opens its own popup (`<dialog>`, the user, same day):
  Apply's holds the signup; the status popup, signed out, says "Sign in to
  check your application status." with a Sign in button that comes back to
  `applicant/#status` and reopens it; signed in it says "Coming soon." for
  now.
- `LGD.auth.signUp` checks again, so the login page's "Create one" obeys
  the same rule.
- 001's `handle_auth_user_confirmed` attaches a confirmed login to the
  person on file and **creates no person otherwise** - it used to create
  an applicant. A signup sent straight to Supabase's API still makes an
  `auth.users` identity, but with no `people` row it reads nothing and
  every page treats it as unconfirmed. So a new staff member is added as a
  person first, then signs up.

`email_on_file` does let anyone test whether an address is on file; that
is what the rule needs, and it says nothing more (no name, no company).

A person on file whose login lands with no role set becomes an `applicant`.
Two consequences worth keeping in mind:

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
back - read your own `people` row (every column but `password_hash`), and
edit your own name and phone. No browser policy can change a role column or
a `manager_id`.

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

**The Supabase dashboard is signed into with GitHub** ("Continue with
GitHub" at supabase.com/dashboard/sign-in, the user, 2026-09-30) - not an
email and password. The project ref is `zglkceocuvioxovbnqrz`; its SQL
editor is supabase.com/dashboard/project/zglkceocuvioxovbnqrz/sql/new,
where the migration files can be pasted in name order instead of running
the script. The script needs only `DATABASE_URL` (in the local `.env`, and
in Render's environment), not a dashboard login. Which GitHub account is
deliberately not written here: this repository is public.

Every file in `supabase/migrations/` is written to be idempotent, so
re-running the set is the normal way to bring a drifted database back into
line. Before applying anything to the live project, run it inside a
transaction and roll back - that is how the trigger and all fifteen RLS rules
in 001 were checked against real data without committing a thing.

Role vocabulary was settled on 2026-09-08: the roles are `admin` / `manager` /
`resident` / `applicant` everywhere - `ROLE_*` in `app/config.py`, and since
2026-09-29 the `is_*` columns of `people`. The old `landlord` / `tenant` values
are mapped forward by `normalize_role()` on every load, and 001's merge (and
`app/db.py`'s `ROLE_COLUMN_MIGRATION`) reads them into the right column.
**Keep that mapping.** A database still holding the old strings - a migration
that has not run yet, a restored backup - must still log people in rather
than reject every user at once.

On 2026-09-08 the last of it went too: `landlords` became `managers`, every
`landlord_id` became `manager_id`, and that table's `company` column became
`name`. `users` became `webusers` in the same pass (merged into `people` on 2026-09-29) - Supabase already has a
`users` table (`auth.users`, where GoTrue keeps identities), and this one is
joined to it, so two tables one schema apart sharing a name was a trap.

Note the collision this leaves, deliberately: `manager` is both a role a
person holds (`people.is_manager`) and the name of the table of
management companies, so a row reads `is_manager=true`, `manager_id='lgd'`.
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

The manager page links to it from step 5, Legal (beside the legal checklist), and it is read there as an ordinary
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
