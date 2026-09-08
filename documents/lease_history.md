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

Nothing is currently pending in red in `documents/lease.md` — every drafted
change above has been reviewed and applied.
