# Legal Research Log

Records the legal sources consulted while drafting or amending lease clauses in
this repo — for future reference, and so an attorney reviewing a clause later (or
presenting on it in litigation) has a trail back to what was actually checked,
when, and how thoroughly.

**This is not legal advice, and nothing here has been verified by an attorney.**
Verification level is noted per source below — several were read via an AI web
search tool's summary rather than opened and read in full by Claude. Before
relying on any entry for litigation, independently pull the primary source
(the URL is given for each) and confirm the citation, holding, and quote.

---

## §18 ATTORNEY'S FEES — dollar-floor increase, 2026-09-06

**Question:** The lease's attorney's-fees clause read "25% of the amount claimed
or a minimum of $100, whichever is greater." Was 25% low for Louisiana, and was
$100 a reasonable floor?

**Conclusion reached:** Keep 25% unchanged. Raise the $100 floor to $500.

**Searches run:**
- WebSearch: "Louisiana residential lease attorney's fees clause percentage
  common 25% enforceability"
- WebSearch: "Louisiana court review stipulated attorney fee percentage lease
  reasonableness reduce"
- WebFetch: `https://nomar.org/wp-content/uploads/2023/11/Residential_Lease_Legal.pdf`

**Sources relied on:**

1. **New Orleans Metropolitan Association of REALTORS® (NOMAR), Standard
   Residential Lease form, revised 08/08.**
   <https://nomar.org/wp-content/uploads/2023/11/Residential_Lease_Legal.pdf>
   **Verification: high** — fetched and read in full (all 4 pages).
   This is the actual industry-standard New Orleans lease form this LGD lease
   appears to be adapted from — nearly every section (Security Deposit, Default/
   Abandonment/Eviction, Other Violations, Occupancy, Signs & Access, Attorney's
   Fees, Other Conditions, Waiver of Notice, Utilities, the "no holes/no painting/
   no waterbeds" miscellaneous list) matches closely in structure and wording.
   Its own Attorney's Fees clause (page 3): *"Such fee is hereby fixed at
   twenty-five (25%) percent of the amount claimed or a minimum of $300.00
   whichever is greater."* Used to establish that 25% is the local standard
   rate (not low), and that even NOMAR's 2008-vintage floor ($300) was already
   three times the $100 in this lease.

2. **First National Bank of Commerce v. Pontchartrain Leasing Co.**
   <https://www.courtlistener.com/opinion/7631360/first-national-bank-of-commerce-v-pontchartrain-leasing-co/>
   **Verification: low — not independently read by Claude.** Surfaced and
   summarized by the WebSearch tool, not opened and read directly. Per that
   summary: a Louisiana court found an attorney's fee of approximately $1,700
   under a stipulated 25% clause excessive for the work involved, and reduced
   it to $1,000. Cited for the general principle that Louisiana courts retain
   authority to reduce a contractually-stipulated attorney's-fee percentage
   as "clearly excessive," regardless of what the lease specifies. **Confirm
   the actual holding, facts, and quote against the opinion itself before
   citing this in any filing.**

3. **Attorney's Fees As An Element of Damages: The General Rule and
   Exceptions** (Louisiana Law Review, LSU).
   <https://digitalcommons.law.lsu.edu/cgi/viewcontent.cgi?article=2804&context=lalrev>
   **Verification: low — not independently read by Claude**, topic only (general
   Louisiana law that parties may contract for attorney's-fee shifting, since
   Louisiana otherwise follows the American Rule where each side bears its own
   fees absent a statute or contract).

**Reasoning applied:** Since 25% already matches the market standard and courts
already review stipulated percentages for excessiveness, raising the percentage
further seemed unlikely to increase actual recovery and risked a court finding
it excessive. The floor was the actually-stale term (below even NOMAR's 2008
figure, let alone its 2026 inflation-adjusted equivalent), so that's what changed.

---

## §13 UTILITIES — per-day penalty increase, 2026-09-06 (approved)

**Question:** The lease charges Lessee "$5 per day per utility" if utilities
aren't transferred into Lessee's name by occupancy. Is $5 too low?

**Change (approved):** Raised $5 to $10 per day per utility.

**Searches run:**
- WebSearch: "lease clause tenant fails to transfer utilities into their name
  per day penalty fee amount landlord"
- WebSearch: "New Orleans average monthly electric water gas utility bill 2026
  residential apartment"

**Sources relied on:**

1. **NOMAR Standard Residential Lease form** (same source as the attorney's-fees
   entry above). **Verification: high** — already read in full. Its own
   UTILITIES clause has **no per-day dollar penalty at all**: *"Lessee shall
   maintain all utility services... in Lessee's name and shall promptly pay all
   charges due thereon."* So unlike the attorney's-fees figure, there is no
   local-standard number to benchmark the $5/day (or $10/day) against — this
   mechanism appears to be a custom addition to the LGD lease, not inherited
   from the NOMAR template.

2. **General web search on per-day utility-transfer penalty clauses.**
   **Verification: low** — synthesized search summary only, no single
   authoritative source opened. Found no standardized industry figure; amount
   varies lease-to-lease. Also surfaced a related (separate) caution: a
   landlord who unilaterally cuts off utilities themselves (rather than
   charging a contractual fee, as this clause does) risks that being treated
   as a self-help/constructive eviction in most jurisdictions — not directly
   about the dollar amount, but relevant context for why a fee-based clause
   (as opposed to landlord self-help) is the safer structure to keep.

3. **New Orleans residential utility cost estimates, 2026** — EnergySage,
   RentCafe, and utility-rates.com listings surfaced by search.
   **Verification: low** — figures are search-engine-reported estimates, not
   pulled from a single authoritative source or independently cross-checked.
   Approximate figures used: electric ~$123/month (~$4.10/day), water (S&WB)
   ~$41–46/month (~$1.40–1.50/day), combined electric+gas+water ~$265–330/month
   (~$8.70–11/day).

**Reasoning applied:** $5/day per utility (~$150/month if never switched)
roughly tracks a single unswitched electric bill, but undershoots if water is
also unswitched, and more importantly is low enough to not meaningfully deter
a tenant from just leaving it unswitched. $10/day gives headroom over any
single utility's estimated real daily cost while staying a defensible,
non-punitive figure tied to actual cost data rather than an arbitrary
escalation. **Status: approved and finalized** — applied to both
`documents/lease.md` and `pandadoc/lease_template_body.md`.
