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

---

## Application §10.1 BINDING ARBITRATION — review, 2026-09-07

**Question:** Is the arbitration clause carried over from the old paper
application accurate, correctly cited, and in the right document?

**Conclusion reached:** The citation is correct. The clause was on the weakest
possible footing where it sat — in the *application* rather than the lease — and
its own recited consideration did not exist at the moment the applicant signed.
**Status: rewritten in place on 2026-09-07, by decision to keep it on the
application rather than move it to the lease.** What changed: the parties are now
Applicant and Owner rather than Lessee and Lessor; the consideration recited is
the Owner's actual review of the application and holding of the apartment, not a
leasing that has not happened; the scope is disputes arising out of the
application and its handling, including a denial and the holding deposit; a
conspicuous plain-language waiver notice was added at the top; the duplicated
"as the case may be" clause was cut; and the statute is now named correctly as
the Louisiana Binding Arbitration Law. The arbitrator-selection mechanics,
timelines, service by certified mail, and the survival provision are unchanged
from the original.

**Still true after the rewrite, and worth an attorney's eye:** it binds a denied
applicant to arbitrate a claim about the denial itself, which remains the
scenario most likely to be challenged. `documents/lease.md` still has no
arbitration clause, so a dispute arising *under the lease* is not covered by
anything.

**Searches run:**
- WebSearch: "Louisiana Revised Statutes 9:4201 arbitration law validity of
  arbitration agreements"
- WebSearch: "pre-dispute binding arbitration clause rental application Fair
  Housing Act discrimination claims enforceability"
- WebSearch: "arbitration clause in rental application before lease signed
  consideration enforceable applicant not tenant"
- WebFetch: `https://www.mintz.com/insights-center/viewpoints/2206/2024-09-04-arbitration-clauses-and-class-action-waivers-residential`

**Sources relied on:**

1. **La. R.S. 9:4201, "Validity of arbitration agreements"** (Justia / FindLaw
   reproductions of the statute).
   <https://law.justia.com/codes/louisiana/revised-statutes/title-9/rs-9-4201/>
   **Verification: medium** — read via search-tool summary of the statute text,
   not opened on legis.la.gov directly.
   Confirms the citation in the application is accurate: 9:4201 is the opening
   section of the Louisiana Binding Arbitration Law (9:4201–4217), and provides
   that a written agreement to arbitrate a future controversy "shall be valid,
   irrevocable, and enforceable, save upon such grounds as exist at law or in
   equity for the revocation of any contract." Enacted Acts 1997, No. 1451, §2.
   Note the statute's own name is the Louisiana **Binding** Arbitration Law; the
   application calls it the "Louisiana Arbitration Law."

2. **Mintz, "Arbitration Clauses and Class Action Waivers in Residential
   Leases: Are They Enforceable?" (2024-09-04).**
   <https://www.mintz.com/insights-center/viewpoints/2206/2024-09-04-arbitration-clauses-and-class-action-waivers-residential>
   **Verification: medium** — fetched, but the page returned only a partial
   summary; key passages were not quoted back in full.
   Arbitration provisions in otherwise valid contracts are generally enforceable
   under the FAA, which preempts contrary state law (*AT&T Mobility v.
   Concepcion*, 2011). Standalone class-action waivers (outside an arbitration
   clause) are the part that varies by state. **Contains no discussion of Fair
   Housing Act claims or of clauses signed at the application stage.**

3. **General practitioner commentary surfaced by search** (National Law Review,
   Multifamily Executive, and California tenant-side firm posts).
   **Verification: low** — search-summary only, not fetched.
   Two recurring points worth keeping: (a) an arbitration provision "should be
   clear, set off, and distinguishable from the rest of the lease and should
   explain its purpose, making clear that by signing, residents are agreeing to
   give up their right to bring a lawsuit in court"; (b) courts decline to
   enforce clauses that reserve litigation for the landlord while forcing the
   tenant into arbitration. California Civil Code §1953 voids lease provisions
   waiving a tenant's procedural litigation rights — cited only as evidence that
   state-level limits exist; **no equivalent Louisiana provision was searched
   for or found, and its absence here should not be read as confirmation that
   none exists.**

**Reasoning applied — problems found, in order of seriousness:**

1. **Wrong document.** The clause opens "For and in partial consideration of
   the leasing of said premises to Lessee, Lessee agrees…" but it sits on the
   *application*. The signer is an applicant, not a Lessee, and the leasing it
   recites as consideration has not happened and may never happen. The clause is
   numbered "10.1", which does not correspond to anything in this application —
   strong evidence it was pasted in from some other lease document.
   `documents/lease.md`, where it would actually belong, **has no arbitration
   clause at all** (its sections run 1–20, none of them arbitration).

2. **Worst case is the likeliest case.** The claim most likely to arise at the
   application stage is a Fair Housing Act claim about the *denial* of the
   application — and this clause purports to push exactly that into arbitration
   while resting on consideration ("the leasing of said premises") that, for a
   denied applicant, never came into existence.

3. **No plain-language waiver notice.** Per the practitioner guidance above, the
   clause should conspicuously tell the signer they are giving up the right to
   sue in court. It is currently an unbroken ~400-word block with no such
   statement and no separate signature or initial line acknowledging the waiver.

4. **Drafting defects** (independent of enforceability): the duplicated and
   truncated clause "as the case may be, arising out of any representatives of
   Lessee, as the case may be, arising out of any and all claims"; and the
   surplus "arising out of any breach… of the Fair Housing Act" framing, which
   describes the *claims covered* rather than any obligation of either party.

**Not researched, and deliberately left open:** whether Louisiana has a
provision analogous to California Civil Code §1953; whether HUD or DOJ take an
enforcement position on pre-dispute arbitration of FHA claims; and whether
Louisiana courts have addressed an arbitration clause signed at the rental
application stage. Any of the three could change the analysis.
