# Lease history

A record of what has actually changed in [`lease.md`](lease.md) and when:
the OCR-era wording corrections made to the scanned original, and every
addition, restructuring and amount change to the lease's terms since.

This is a record, not an instruction. The rules about *making* such a
change - that altering the wording is a legal decision rather than a typo
fix, and that anything drawing on outside research gets logged - live in
[`../CLAUDE.md`](../CLAUDE.md). Append here when a change is made; nothing
already written down gets edited, since the point is what was done at the
time.


## OCR-era wording corrections

Eight were reviewed and corrected by the user on 2026-09-06 in
`documents/lease.md`. Section numbers below are **current** (post-2026-09-07
PARKING move, see the changelog below):

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


## Clause changes changelog

**Entries before 2026-09-08 mention `pandadoc/lease_template_body.md`, which no
longer exists.** PandaDoc was removed that day along with the whole e-signature
path; the file was generated from `documents/lease.md`, so anything an entry
says was "applied identically" to both now lives in `documents/lease.md` alone.
They also point at sections "above" that live in
[`../CLAUDE.md`](../CLAUDE.md) - "A blank, printable paper lease" is there.
The entries are left as written rather than edited, because they are a record
of what was actually done at the time.

Additions, restructuring, and amount changes to lease terms — as opposed to
the wording-error corrections table above. See [`manager/LEGAL_RESEARCH.md`](manager/LEGAL_RESEARCH.md)
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

- **2026-09-19 - §6 SMOKING, opening sentence simplified** (the user's exact
  wording). "No smoking of any kind, including but not limited to cigarettes,
  cigars, pipes, e-cigarettes or vaping devices, and marijuana, is permitted at
  any time inside the leased premises" became "No smoking or vaping of any kind
  is permitted at any time inside the leased premises". The enumerated list of
  methods is gone, and with it the express mention of marijuana; vaping is now
  named alongside smoking rather than as an instance of it. The rest of the
  section is untouched - cost recovery still tied to the §3 security deposit,
  violation still ipso facto default with no §9 five-day cure. Note flagged to
  the user at the time and deliberately left alone: the cost-recovery sentence
  still reads "made necessary by smoking inside the premises", which the old
  opening swept vaping into by definition and the new one no longer does.
  Applied to `documents/lease.md`; `documents/print/lease_print.html`
  regenerated from it.

- **2026-09-19 - §6 SMOKING, cost-recovery sentence matched to the new opening**
  (approved by the user, same day, immediately after the entry above). "equipment
  made necessary by smoking inside the premises" became "equipment made necessary
  by smoking or vaping inside the premises" - two words, nothing else in the
  sentence moved. This closes the gap flagged in the entry above: once the opening
  sentence stopped defining vaping as a kind of smoking and began naming it as a
  separate activity, the bare word "smoking" here no longer reached vape residue,
  which is exactly the damage the sentence exists to bill for. The paragraph was
  re-wrapped to the file's ~87-column body width in the same pass, so the diff
  touches more lines than the two changed words. Applied to `documents/lease.md`;
  `documents/print/lease_print.html` regenerated from it.

- **2026-09-28 - New §20 PLASTER WALLS; PARKING renumbered §20 -> §21**
  (requested by the user). The user supplied a ChatGPT-drafted "Plaster Wall
  Protection Addendum" and asked for it as a lease section in the lease's own
  terms rather than an addendum. Drafted from its points: the addendum's own
  header (date, parties and premises blanks) and "By signing below"
  acknowledgement were dropped, since the lease already carries all of that;
  "Landlord/Tenant" became "Lessor/Lessee"; its sub-headings became lead-in
  sentences. The opening keeps the draft's "historical or delicate plaster"
  and "modern drywall" (restored at the user's request after a shorter
  "plaster, not drywall"). Kept from the original, at the user's direction after a first,
  shorter prose draft: both hardware lists as bullet lists, item for item,
  with "Floreat-style hangers" as the example plaster hook; the 3d
  finish-nail limit; a weight limit without Lessor's written consent - the
  draft's five (5) pounds, raised by the user to **eight (8) pounds** - with
  any heavier item installed or supervised by Lessor so it is anchored into
  the lath or studs. The draft's last two parts, "No Unauthorized Wall
  Repairs" and "Damages and Security Deposit", are its own wording verbatim
  (the user's instruction), with only Tenant/Landlord changed to
  Lessee/Lessor - so repair costs "will be deducted from the Lessee's
  security deposit", not the "may be deducted ... as provided in Section 3"
  of §6 SMOKING, and the patching ban reads "upon move-out". One addition
  inside the verbatim text, at the user's earlier request: "keys breaking"
  is followed by "(the plaster behind the wall that grips the wooden lath
  and holds the wall in place)". The bullets are the first list in the lease; the generator
  renders each "• " paragraph with a hanging indent.
  Inserted before PARKING so PARKING stays the last section, renumbering it
  to §21; nothing in the lease referred to §20 by number. Not reviewed by an
  attorney. The section prints on every lease and is crossed out for every
  address except 1523 St. Andrew (see `documents/properties.json`). Applied
  to `documents/lease.md`; `documents/print/lease_print.html` regenerated
  from it.

- **2026-09-28 - §17 PATIO/YARD split into versions (A) and (B)** (requested
  by the user). The existing wording, unchanged, became "(A)": Lessee
  maintains the patio/yard and alley up to the gate, Lessor the front yard
  and side walk. A new "(B)", drafted to the user's instruction that Lessor
  maintains all and approved by them: "The patio/yard, alley, front yard and
  side walk maintenance is the Lessor's responsibility. This includes, but
  is not limited to, keeping it clean and weed/vegetation control." A's
  "pet waste" was deliberately left out of B - flagged, and the user
  confirmed B properties will not have pets. Both print on every lease and
  the one not applying to the address is crossed out: A for 1534 and 1536
  Camp and 1428 and 1430 Melpomene, B for the rest (see
  `documents/properties.json`). Applied to `documents/lease.md`;
  `documents/print/lease_print.html` regenerated from it.

- **2026-09-28 - §20 PLASTER WALLS became §20 WALLS, with a standard
  version (A) for every lease** (requested by the user, same day). The user
  wanted §17, §20 and §21 on every lease with consistent numbers, each
  lease showing only its own version rather than crossing out the others.
  So §20 is now on every lease: "(A)" is new, drafted from the user's
  points ("No stickers, scratches, or nail holes other than small nail
  holes", and no adhesives as in the plaster wording): "Lessee shall not
  put stickers on, scratch, or make holes in any wall or ceiling, other than
  small nail holes for hanging pictures. Lessee shall not use adhesive
  hooks, mounting tape, Command strips, or poster putty on any wall or
  ceiling. Adhesives frequently pull away the paint and the wall surface
  beneath it." "(B)" is the plaster wording above, unchanged; only 1523 St.
  Andrew gets it. The heading changed from PLASTER WALLS to WALLS to cover
  both. Applied to `documents/lease.md`; `documents/print/lease_print.html`
  regenerated from it.

- **2026-09-28 - Command Strips named as an example, in both §20 versions**
  (requested by the user). "adhesive hooks, mounting tape, Command strips,
  or poster putty" became "adhesive hooks (such as Command Strips), mounting
  tape, or poster putty" in (A), and the same in (B)'s bullet - Command
  Strips now an example of an adhesive hook rather than an item of its own.

- **2026-09-28 - Printed lease header: LLC became Inc** (requested by the
  user). The company name heading the printed lease and its "Page X of Y"
  lines changed from "Lower Garden District Properties LLC" to "Lower Garden
  District Properties Inc". `lease.md` itself does not name the company, so
  only `documents/print/generate_print_lease.py` changed;
  `documents/print/lease_print.html` regenerated.

Nothing is currently pending in red in `documents/lease.md` — every drafted
change above has been reviewed and applied.
