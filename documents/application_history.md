# Application history

A record of what has changed in [`application.md`](application.md) and when,
kept the same way as [`lease_history.md`](lease_history.md). The scanned
originals are in [`originals/`](originals/) and are never edited. Append here
when a change is made; nothing already written down gets edited.

Changes made before this file existed - applying the handwritten notes on
`originals/application_original.pdf` (no application fee, a holding deposit,
"Previous Landlord" wording, occupants by name and email, emergency contact
moved to the front, the arbitration clause rewritten in plain language) - are
in git history.

## Changelog

- **2026-09-28 - Header moved to the generator.** `application.md`'s own
  first lines ("Lower Garden District Properties LLC", "Application for
  Apartment", a `{contact info}` placeholder) were removed: the printed form
  now gets the same header as the lease from
  `print/generate_print_application.py`. The user decided against any
  contact line under it.

- **2026-09-28 - The user's review of suggested improvements.**
  - **Removed:** "Marital status"; the bank "Account #" (the bank reference
    name stays); the "[ ] Child" box on each occupant row (occupants stay
    listed by name and email on every application, deliberately redundant
    with each person's own application).
  - **Added, vehicles:** "Vehicles to be parked at the property (parking is
    limited to vehicles listed here):" and two rows of Make / Model / Color /
    Plate # / State. They show only for an address with parking (1364 Camp
    today), because lease §21 limits parking to "tenant's automobiles listed
    on application".
  - **Added, credit check:** "CREDIT CHECK AUTHORIZATION: I authorize Lessor
    and its agent to obtain a consumer credit report on me and to verify the
    information in this application, including my rental and employment
    history. Applicant's initials____". Drafted wording; not reviewed by an
    attorney.
  - **Terminology:** "owner"/"Owner" became "Lessor" throughout, and "his
    agent" became "its agent", to match the lease and security deposit.
  - **Kept as is, by decision:** Social Security #, the pets question,
    present-address-only history; the holding deposit and arbitration
    wording are left for a later legal review.
  - **Popup:** optional boxes for monthly rental rate, term of lease and
    security deposit, which fill those blanks when typed in.

- **2026-09-28 - Pets question: "NO" became "No"** (the user), to match "Yes".

- **2026-09-29 - Money labels formatted the same** (the user): every label
  for an amount now ends in "$" before its blank, as "Security deposit $"
  already did - "Monthly rental rate" became "Monthly rental rate $",
  "Monthly rent" became "Monthly rent $", and "Monthly salary" became
  "Monthly salary $". The holding deposit's "the sum of $____" already had
  it. In the popup, the rent and deposit boxes accept only digits, "$" and
  ".", start with "$", and keep a single "$" however many are typed.

- **2026-10-02 - Company name: "LGD (Lower Garden District Properties),
  Inc."** (the user, for everything; it was "Lower Garden District
  Properties, Inc."). Changed in `generate_print_lease.py`'s
  `COMPANY_NAME`, which every printed document shares - the header, the
  "Page X of Y" lines and, on the lease, the Lessor blank. No wording in
  the master changed. Every printed document regenerated; page counts at
  every address unchanged.
