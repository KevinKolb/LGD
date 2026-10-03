# Security deposit history

A record of what has actually changed in
[`security_deposit.md`](security_deposit.md) and when, kept the same way as
[`lease_history.md`](lease_history.md). The scanned original and its verbatim
transcript are in [`originals/`](originals/) and are never edited. Append here
when a change is made; nothing already written down gets edited.

## Changelog

- **2026-09-28 - Live master created** (requested by the user). Started as
  `originals/security_deposit_transcript_verbatim.md` word for word, minus
  the original's letterhead (Steve A. Hartnett, 1556 Camp Street, New Orleans,
  LA 70130, 504-524-6260) and its "SECURITY DEPOSIT AGREEMENT" title: the
  generator prints LGD's header in their place - "LGD PROPERTIES, INC" over
  "SECURITY DEPOSIT AGREEMENT", the user's wording.

- **2026-09-28 - Conditions 6 and 9 made address-specific, to match the
  lease** (requested by the user: "make the security deposit agreement
  address specific and match lease"). Each now has an (A) and a (B) version,
  chosen by the same apartment setting as the lease, so a deposit never
  contradicts its lease. The numbering does not change.
  - **6 (walls, lease §20).** Was "No stickers, scratches, or holes, other
    than small nail holes." (A), standard walls: "No stickers, scratches, or
    holes, other than small nail holes, and no adhesive hooks (such as Command
    Strips), mounting tape, or poster putty used on any wall or ceiling." (B),
    plaster: "No damage to the plaster walls or ceilings, and no hardware,
    adhesives, weight, or repairs other than as permitted by Section 20 of the
    lease."
  - **9 (yard, lease §17).** Was "Patio/yard has been cleaned; including, but
    not limited to, pet waste and vegetation." (A), Lessee maintains: "Patio/
    yard and alley up to the gate have been cleaned; including, but not limited
    to, pet waste and vegetation." (B), Lessor maintains all: "Patio/yard
    maintenance is Lessor's responsibility under Section 17 of the lease; this
    condition does not apply."
  Drafted to match the lease sections they point to; not reviewed by an
  attorney.

- **2026-09-28 - Condition 6 (B), plaster, reworded** (requested by the user:
  word it better, name excessive weight and the like, and include everything
  the standard walls rule covers). Was "No damage to the plaster walls or
  ceilings, and no hardware, adhesives, weight, or repairs other than as
  permitted by Section 20 of the lease." Now: "No stickers, scratches, or
  holes, other than small nail holes made as permitted by the lease, and no
  adhesive hooks (such as Command Strips), mounting tape, or poster putty used
  on any wall or ceiling. No cracking, crumbling, or other damage to the
  plaster walls or ceilings from large nails, screws, anchors, or heavy-duty
  mounting hardware; from excessive weight, including any item over eight (8)
  pounds hung without Lessor's prior written consent; or from patching,
  spackling, or painting by Lessee." Its first sentence is (A) word for word
  but for "made as permitted by the lease". It no longer cites "Section 20",
  since the lease at 1523 may be one signed before §20 existed, whose plaster
  rules come from the Plaster Walls Addendum.

- **2026-09-28 - Header company name** changed from "LGD PROPERTIES, INC" to
  "Lower Garden District Properties, Inc.", the name the user set for every
  document. The deposit now takes it from the lease generator's COMPANY_NAME,
  so the two cannot differ again.

- **2026-09-29 - An Email line beside each Lessee signature** (the user:
  every place a lessee writes their name, they give their email too), in
  both sets of three - under the deposit terms and under the holding
  deposit. Filled in by hand; no wording changed, and the form is still
  two pages.

- **2026-10-02 - Company name: "LGD (Lower Garden District Properties),
  Inc."** (the user, for everything; it was "Lower Garden District
  Properties, Inc."). Changed in `generate_print_lease.py`'s
  `COMPANY_NAME`, which every printed document shares - the header, the
  "Page X of Y" lines and, on the lease, the Lessor blank. No wording in
  the master changed. Every printed document regenerated; page counts at
  every address unchanged.

- **2026-10-03 - Company name: "LGD (Lower Garden District) Properties,
  Inc."** (the user, "everywhere"; it was "LGD (Lower Garden District
  Properties), Inc."). Changed in `generate_print_lease.py`'s
  `COMPANY_NAME`, which every printed document shares. No wording in the
  master changed. Every printed document regenerated; page counts at every
  address unchanged.
