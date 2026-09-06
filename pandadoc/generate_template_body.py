#!/usr/bin/env python3
"""Generate `pandadoc/lease_template_body.md` from `originals/lease.md`.

`originals/lease.md` is the single, human-editable source of the lease's
wording — see CLAUDE.md. This script is the only thing that should ever write
`pandadoc/lease_template_body.md`; nobody should hand-edit that file, because
it would silently drift out of sync with `lease.md` the next time this script
runs, and a stale template is exactly the kind of mistake that matters in a
legal document.

Usage:
    python pandadoc/generate_template_body.py

What it does:
    1. Reads originals/lease.md.
    2. Drops the scan-page artifacts ("## PAGE N" headings and the "---"
       dividers between them) - PandaDoc doesn't care about the original
       scan's page boundaries; its own page breaks are configured separately,
       in its editor, once real content and formatting are known.
    3. Replaces each blank (a run of 3+ underscores) with the matching
       PandaDoc token, e.g. "___" -> "[Lessor.Name]". Matching is done by
       surrounding text, not by position, and every expected blank must be
       found exactly once or the script fails loudly - a missing or moved
       blank should stop the build, not produce a silently wrong template.
    4. Drops the literal signature-line blanks at the end (those become
       drag-and-drop Signature/Date fields in PandaDoc, never text) and
       replaces them with a fixed guidance section instead.
    5. Wraps the result in a header/footer that documents where the content
       came from and what's still a manual step in PandaDoc's editor
       (page size, margins, fonts, page breaks, footers - none of which can
       be expressed in a plain text file).

If you need to add a new blank (a new fill-in field) to the lease: add it to
BLANK_SUBSTITUTIONS below in document order, add the token to app/lease.py's
LeaseRequest.tokens(), and add a row to the token table this script generates.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE = REPO_ROOT / "originals" / "lease.md"
OUTPUT = REPO_ROOT / "pandadoc" / "lease_template_body.md"

BLANK = r"_{2,}"  # a fill-in blank: two or more underscores (the shortest
                  # is the execution block's 2-digit year, "20__")

# Each entry: (regex matched against the fully-flattened lease body, exact
# replacement text). Applied in document order - each consumes the *first*
# remaining match, so order matters. `BLANK` stands for one blank; write the
# surrounding words literally so the match can only land on the right blank.
BLANK_SUBSTITUTIONS: list[tuple[str, str]] = [
    (
        rf"{BLANK}\(hereinafter referred to as Lessor\) hereby leases to",
        "[Lessor.Name] (hereinafter referred to as Lessor) hereby leases to",
    ),
    (
        rf"hereby leases to\s+{BLANK}\s+\(hereinafter referred to as Lessee\)",
        "hereby leases to [Lessee.Names] (hereinafter referred to as Lessee)",
    ),
    (
        rf"the premises known as {BLANK}",
        "the premises known as [Premises.Address]",
    ),
    (
        rf"commencing on the {BLANK} day of {BLANK} 20{BLANK},",
        "commencing on the [Term.StartDay] day of [Term.StartMonth] "
        "20[Term.StartYear],",
    ),
    (
        rf"ending on the last day of {BLANK} 20\s*{BLANK}\.",
        "ending on the last day of [Term.EndMonth] 20[Term.EndYear].",
    ),
    (
        rf"monthly rental of{BLANK}dollars",
        "monthly rental of [Rent.Monthly] dollars",
    ),
    (
        rf"net rental of {BLANK}\s+dollars",
        "net rental of [Rent.Discounted] dollars",
    ),
    (
        rf"the sum of {BLANK} dollars",
        "the sum of [Deposit.Amount] dollars",
    ),
    (
        rf"occupied by the following persons only\s+{BLANK}\s+{BLANK}",
        "occupied by the following persons only\n\n[Occupants.List]",
    ),
    (
        rf"except {BLANK}\.",
        "except [Utilities.Excluded].",
    ),
    (
        rf"Executed in duplicate at {BLANK}, Louisiana this {BLANK} day of "
        rf"{BLANK}20{BLANK}\.",
        "Executed in duplicate at [Execution.City], Louisiana this "
        "[Execution.Day] day of [Execution.Month] 20[Execution.Year].",
    ),
]

EXPECTED_TOKENS = [
    "Lessor.Name", "Lessee.Names", "Premises.Address",
    "Term.StartDay", "Term.StartMonth", "Term.StartYear",
    "Term.EndMonth", "Term.EndYear",
    "Rent.Monthly", "Rent.Discounted",
    "Deposit.Amount", "Occupants.List", "Utilities.Excluded",
    "Execution.City", "Execution.Day", "Execution.Month", "Execution.Year",
]

TOKEN_FILLS = {
    "Lessor.Name": "Lessor on the opening line",
    "Lessee.Names": "Tenant names on the opening line",
    "Premises.Address": '"the premises known as ___"',
    "Term.StartDay": '§1 "the ___ day of"',
    "Term.StartMonth": "§1 start month",
    "Term.StartYear": "§1 start year, last two digits",
    "Term.EndMonth": '§1 "ending on the last day of ___"',
    "Term.EndYear": "§1 end year, last two digits",
    "Rent.Monthly": "§2 monthly rental",
    "Rent.Discounted": "§2 net rental if paid on time",
    "Deposit.Amount": "§3 security deposit",
    "Occupants.List": "§4 occupants",
    "Utilities.Excluded": '§14 "except ___"',
    "Execution.City": "Execution block city",
    "Execution.Day": "Execution block day",
    "Execution.Month": "Execution block month",
    "Execution.Year": "Execution block year, last two digits",
}

HEADER = """# PandaDoc template body — Residential Lease

**GENERATED FILE — do not hand-edit.** Regenerate with:

    python pandadoc/generate_template_body.py

Wording is derived automatically from [`originals/lease.md`](../originals/lease.md)
— the live working copy of the lease — with each blank replaced by a PandaDoc
token in `[Group.Name]` form. To change the wording, edit `originals/lease.md`,
then re-run the generator; never edit this file directly, or the next
regeneration will silently discard the edit.

If an apparent typo turns up in the lease text, don't "fix" the spelling here:
decide deliberately in `originals/lease.md` first (see `CLAUDE.md`'s
wording-corrections table for the review already done), record it there, then
regenerate.

## Tokens

Confirm under PandaDoc's **Manage → Tokens** that all {count} appear:

| Token | Fills |
| --- | --- |
{token_rows}

The years are two digits because the lease pre-prints `20__`. The app sends `26`
for 2026 — do not add another `20` in the template.

---
"""

FOOTER = """
---

## Signature block

Do not type these as text. Drag PandaDoc **Signature** fields onto the page and
assign each to the role named below, then add a **Date** field beside each one.

| Line on the paper lease | Assign field to role | Required? |
| --- | --- | --- |
| Lessor/Agent | `Lessor` | Yes |
| Lessee (first line) | `Lessee` | Yes |
| Lessee (second line) | `Lessee2` | Optional |
| Lessee (third line) | `Lessee3` | Optional |

The app sends the `Lessor` role at `signing_order` 1 and every tenant at
`signing_order` 2, so the landlord signs first and all tenants are then
unblocked at once.

## Print layout — configure manually in the PandaDoc editor

This file carries wording only. Page size, margins, fonts, page breaks, and
headers/footers are all PandaDoc editor settings — none of them can be
expressed in a plain text file, so they don't get regenerated automatically.
Before the template is final:

- Set page size to **US Letter** under Page properties. PandaDoc also offers
  Legal, A4, A3, and Slide — its default may not be Letter.
- Set margins (roughly 1") and a legible body font under Page properties /
  Format > Theme. PandaDoc ships 6 built-in fonts, or a custom Google Font.
- Add a footer with page numbers (Format > Theme > Page > Header and Footer).
  Page numbers only render in the **downloaded PDF**, not in the editor view
  — don't be alarmed if you don't see them while building the template.
- Insert explicit **Page Break** blocks between sections, then use PandaDoc's
  PDF page-break estimator to check two things: no numbered section heading
  is left alone at the bottom of a page with its own body text starting on
  the next one, and the whole execution block (the "Executed in duplicate..."
  line plus every signature line) stays together on one final page.
- Consider a **Lessee's Initials / Lessor's Initials** line at the bottom of
  each page, the way the NOMAR standard lease this template is based on does
  (see `LEGAL_RESEARCH.md`) — protects against a page being swapped after
  signing. Add it with PandaDoc Initial fields once you know where pages
  actually fall; a script can't predict that from outside the editor.
"""


def flatten_paragraph(text: str) -> str:
    """Collapse hard line-wraps within a paragraph into single spaces.

    `lease.md` hard-wraps prose at ~90 columns for readability in a plain
    text editor; that wrapping carries no meaning (Markdown already treats
    a single newline as a space) and only gets in the way of matching a
    blank that happens to fall across a line break. Blank lines (paragraph
    boundaries) are preserved.
    """
    return re.sub(r"[ \t]*\n[ \t]*", " ", text).strip()


SENTENCE_END = re.compile(r'[.!?:]["\')]?$')


def extract_body(source_text: str) -> str:
    """Pull the lease body out of lease.md: drop the title and page markers.

    A blank line in `lease.md` is not reliably a real paragraph break: the
    scanned document's page cuts sometimes fall mid-sentence (e.g. the
    SECURITY DEPOSIT and OTHER VIOLATIONS AND NUISANCES sections), and the
    preamble has a purely stylistic blank line splitting one sentence. Rather
    than trust blank lines alone, a kept block that doesn't end in sentence-
    final punctuation is merged into the next one - that's the actual signal
    that a "paragraph break" wasn't semantic.
    """
    # Split on blank-line-delimited blocks so real paragraph boundaries survive.
    blocks = re.split(r"\n\s*\n", source_text.strip())
    kept: list[str] = []
    for block in blocks:
        stripped = block.strip()
        if not stripped:
            continue
        if stripped.startswith("# "):
            continue  # the "# LGD Residential Lease" title
        if stripped == "---":
            continue  # scan-page-boundary divider, meaningless to PandaDoc
        if re.match(r"^## PAGE \d+$", stripped):
            continue  # scan-page marker, meaningless to PandaDoc
        kept.append(flatten_paragraph(stripped))

    starts_new_section = re.compile(r"^\d+\.\s*\*\*")
    merged: list[str] = []
    for block in kept:
        continues_prior = (
            merged
            and not SENTENCE_END.search(merged[-1])
            and not starts_new_section.match(block)
        )
        if continues_prior:
            merged[-1] = f"{merged[-1]} {block}"
        else:
            merged.append(block)
    return "\n\n".join(merged)


def split_off_signature_block(body: str) -> str:
    """Drop the four literal signature-line blanks; they become PandaDoc
    Signature/Date fields, never text. Everything up to and including the
    execution sentence is kept.
    """
    marker = "Executed in duplicate at"
    index = body.find(marker)
    if index == -1:
        raise SystemExit(
            "Could not find the execution sentence "
            f"({marker!r}) in originals/lease.md - has it moved or changed?"
        )
    end_of_sentence = body.find(".", index)
    if end_of_sentence == -1:
        raise SystemExit("Execution sentence has no closing period - malformed?")
    return body[: end_of_sentence + 1]


def apply_substitutions(body: str) -> tuple[str, list[str]]:
    """Replace each blank with its token, in order. Returns (text, tokens used)."""
    used: list[str] = []
    for pattern, replacement in BLANK_SUBSTITUTIONS:
        match = re.search(pattern, body)
        if match is None:
            raise SystemExit(
                "Could not find an expected blank in originals/lease.md.\n"
                f"  Looking for pattern: {pattern!r}\n"
                "  The wording around a blank may have changed - update this "
                "script's BLANK_SUBSTITUTIONS to match, or fix the lease text."
            )
        body = body[: match.start()] + replacement + body[match.end():]
        used.extend(re.findall(r"\[([A-Za-z.]+)\]", replacement))
    return body, used


def check_no_blanks_remain(body: str) -> None:
    """After substitution, no fill-in blank should remain in the body text.

    A leftover blank means a fill-in field exists in `lease.md` that this
    script doesn't know how to translate - almost certainly a bug, not
    something to paste into PandaDoc silently missing a token.
    """
    remaining = re.findall(BLANK, body)
    if remaining:
        raise SystemExit(
            f"{len(remaining)} unhandled blank(s) remain after substitution. "
            "Add a BLANK_SUBSTITUTIONS entry for whatever changed in "
            "originals/lease.md, or this script has a bug."
        )


def check_all_tokens_used(used_tokens: list[str]) -> None:
    if sorted(used_tokens) != sorted(EXPECTED_TOKENS):
        missing = set(EXPECTED_TOKENS) - set(used_tokens)
        extra = set(used_tokens) - set(EXPECTED_TOKENS)
        detail = []
        if missing:
            detail.append(f"missing: {sorted(missing)}")
        if extra:
            detail.append(f"unexpected: {sorted(extra)}")
        raise SystemExit(f"Token mismatch after generation - {'; '.join(detail)}")


def render_header() -> str:
    rows = "\n".join(
        f"| `{token}` | {TOKEN_FILLS[token]} |" for token in EXPECTED_TOKENS
    )
    return HEADER.format(count=len(EXPECTED_TOKENS), token_rows=rows)


def generate(source_text: str) -> str:
    body = extract_body(source_text)
    body = split_off_signature_block(body)
    body, used_tokens = apply_substitutions(body)
    check_no_blanks_remain(body)
    check_all_tokens_used(used_tokens)
    return render_header() + "\n" + body + "\n" + FOOTER


def main() -> None:
    if not SOURCE.is_file():
        raise SystemExit(f"{SOURCE} does not exist.")
    output = generate(SOURCE.read_text(encoding="utf-8"))
    OUTPUT.write_text(output, encoding="utf-8")
    print(f"Wrote {OUTPUT} from {SOURCE} ({len(EXPECTED_TOKENS)} tokens).")


if __name__ == "__main__":
    main()
