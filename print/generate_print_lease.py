#!/usr/bin/env python3
"""Generate a self-contained, print-ready HTML lease from `originals/lease.md`.

Same idea as `pandadoc/generate_template_body.py`: `originals/lease.md` is the
only file anyone edits; this script derives a *different* output from it -
here, a blank paper lease meant to be opened in any browser and printed
(Ctrl+P / Cmd+P), rather than pasted into PandaDoc.

Unlike the PandaDoc version, blanks stay as literal blank lines (there's no
tenant yet to fill a token with) and the signature lines stay as real
underscore lines too - this is meant to be signed by hand on paper.

Usage:
    python print/generate_print_lease.py

No third-party dependencies: the output is one HTML file with its CSS
inline, so it prints correctly offline, from any browser, on any machine -
nothing to install.
"""
from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Iterator

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE = REPO_ROOT / "originals" / "lease.md"
OUTPUT = REPO_ROOT / "print" / "lease_print.html"

# Reused verbatim from pandadoc/generate_template_body.py's approach: a blank
# line in lease.md is not reliably a real paragraph break (the scanned
# document's page cuts sometimes fall mid-sentence), so a block that doesn't
# end in sentence-final punctuation gets merged into the next one.
SENTENCE_END = re.compile(r'[.!?:]["\')]?$')
STARTS_NEW_SECTION = re.compile(r"^\d+\.\s*\*\*")
BLANK = re.compile(r"_{2,}")

# The title's company-specific branding becomes a blank (see .title-blank in
# the CSS below), per the request: this lease is shared across multiple
# landlords, so no single landlord's name belongs in a document title meant
# to be reused by all of them.

HTML_HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="/favicon.ico">
<title>Residential Lease</title>
<style>
  @page {
    size: letter;
    margin: 0.85in;
    @bottom-center {
      content: "Page " counter(page) " of " counter(pages);
      font-family: Georgia, "Times New Roman", Times, serif;
      font-size: 9pt;
      color: #444;
    }
  }
  html, body {
    margin: 0;
    padding: 0;
    background: #fff;
    color: #000;
  }
  html {
    /* Phones inflate the font of long text blocks ("text autosizing"),
       and printing from the phone carries that inflation onto paper -
       which is why this printed longer from a phone than from a desktop.
       Pin it so a point is a point on every device. */
    -webkit-text-size-adjust: 100%;
    text-size-adjust: 100%;
  }
  body {
    font-family: Georgia, "Times New Roman", Times, serif;
    font-size: 11.5pt;
    line-height: 1.4;
    max-width: 7.5in;
    margin: 0 auto;
    padding: 0.25in 0 1in;
  }
  .title-blank {
    display: block;
    border-bottom: 1px solid #000;
    height: 1.1em;
    margin: 0 auto 0.15in;
    max-width: 5.5in;
  }
  h1.subtitle {
    text-align: center;
    font-size: 15pt;
    letter-spacing: 0.06em;
    margin: 0 0 0.5in;
    font-weight: bold;
  }
  p {
    margin: 0 0 0.85em;
    text-align: justify;
    /* Not supported by Firefox as of early 2026 (same gap as the page
       counter below) - it just prints without this refinement there. */
    orphans: 3;
    widows: 3;
  }
  p.section {
    page-break-after: avoid;
  }
  .blank {
    display: inline-block;
    min-width: 2.4em;
    border-bottom: 1px solid #000;
  }
  .blank.long { min-width: 5.5in; }
  .blank.medium { min-width: 3in; }
  .blank.word { min-width: 1.3in; }
  .blank.short { min-width: 1.4em; }
  .blank.tiny { min-width: 0.9em; }
  p.preamble {
    /* Three name/address blanks packed into one short sentence stretch
       justified text into odd gaps; left-aligned, uneven line lengths
       read as normal rather than "wrong". */
    text-align: left;
  }
  label.checkbox-line {
    font-weight: normal;
  }
  label.checkbox-line input {
    margin-right: 0.35em;
  }
  .checkbox-line.struck {
    text-decoration: line-through;
    color: #555;
  }
  .signature-block {
    page-break-inside: avoid;
    page-break-before: avoid;
    margin-top: 0.3in;
  }
  .sig-line {
    margin-top: 0.3in;
    border-top: 1px solid #000;
    max-width: 4.2in;
    padding-top: 0.12em;
    font-size: 10pt;
    letter-spacing: 0.04em;
  }
  .footer-note {
    margin-top: 0.6in;
    padding-top: 0.2in;
    border-top: 1px solid #999;
    font-size: 8.5pt;
    color: #444;
    page-break-inside: avoid;
  }
  @media print {
    .footer-note { display: none; }
    a { color: inherit; text-decoration: none; }
    /* Let the page box from @page decide the column width, rather than
       the screen sizing above. A phone lays the screen out ~390px wide,
       and a browser that prints from that layout rather than re-flowing
       to paper width would wrap far more lines per paragraph, adding
       pages. Anchoring the printed width to the paper keeps the
       pagination identical everywhere. */
    body {
      width: auto;
      max-width: none;
      margin: 0;
      padding: 0 0 0.25in;
    }
  }
  @media screen {
    body { padding: 0.5in 0.75in 1in; box-shadow: 0 0 12px rgba(0,0,0,.15); }
  }
</style>
</head>
<body>
<span class="title-blank" aria-hidden="true"></span>
<h1 class="subtitle">RESIDENTIAL LEASE</h1>
"""

HTML_FOOTER = """
<div class="footer-note">
  This is a blank lease generated from <code>originals/lease.md</code> by
  <code>print/generate_print_lease.py</code> for printing and hand-filling on
  paper. It will not appear on a printed copy (hidden in print styles).
  Regenerate after editing <code>originals/lease.md</code>. The "Page X of Y"
  footer is a CSS page-number counter: it renders correctly when printed from
  Chrome, Edge, or Safari (18.2+), but not from Firefox, which does not yet
  support this CSS feature as of early 2026 - if you print from Firefox, that
  footer will simply be missing rather than wrong.
</div>
<script>
  // Opening this page (from the dashboard's "Print blank lease" button) is
  // the whole point of the page, so bring up the browser's print dialog
  // automatically rather than making the landlord find Ctrl+P themselves.
  // The small delay lets layout settle first so the print preview is right.
  window.addEventListener("load", () => setTimeout(() => window.print(), 150));

  // Pick one of the two PARKING radio buttons first (cancel the print
  // dialog above if it beat you to it, then print again with Ctrl+P/
  // Cmd+P) to cross out whichever option doesn't apply.
  function updateParkingStrikes() {
    var notAvailable = document.getElementById("parking-not-available");
    var limited = document.getElementById("parking-limited");
    document.getElementById("parking-label-not-available").classList.toggle("struck", limited.checked);
    document.getElementById("parking-label-limited").classList.toggle("struck", notAvailable.checked);
  }
  document.getElementById("parking-not-available").addEventListener("change", updateParkingStrikes);
  document.getElementById("parking-limited").addEventListener("change", updateParkingStrikes);

  // ?parking=yes / ?parking=no preselects one of the two options, so the
  // page is already correct by the time the print dialog opens. The
  // manager dashboard's "Print paper lease" button asks the question and
  // appends this; opening the page without it leaves both unpicked, to be
  // filled in by hand or clicked here.
  var parking = new URLSearchParams(window.location.search).get("parking");
  if (parking === "yes") {
    document.getElementById("parking-limited").checked = true;
  } else if (parking === "no") {
    document.getElementById("parking-not-available").checked = true;
  }
  updateParkingStrikes();
</script>
</body>
</html>
"""

def flatten_paragraph(text: str) -> str:
    return re.sub(r"[ \t]*\n[ \t]*", " ", text).strip()


def extract_body_blocks(source_text: str) -> list[str]:
    """Same merge logic as the PandaDoc generator - see its docstring."""
    blocks = re.split(r"\n\s*\n", source_text.strip())
    kept: list[str] = []
    for block in blocks:
        stripped = block.strip()
        if not stripped:
            continue
        if stripped.startswith("# "):
            continue
        if stripped == "---":
            continue
        if re.match(r"^## PAGE \d+$", stripped):
            continue
        kept.append(flatten_paragraph(stripped))

    merged: list[str] = []
    for block in kept:
        continues_prior = (
            merged
            and not SENTENCE_END.search(merged[-1])
            and not STARTS_NEW_SECTION.match(block)
        )
        if continues_prior:
            merged[-1] = f"{merged[-1]} {block}"
        else:
            merged.append(block)
    return merged


def split_source(source_text: str) -> tuple[str, str]:
    """Split the RAW source into (everything through the execution sentence,
    everything after it) - done before any paragraph-merge logic runs.

    The merge logic in `extract_body_blocks` is right to glue together prose
    that doesn't end in a period, but the signature tail is not prose: a
    blank line and a role label like "Lessor/Agent" both fail the
    "ends in a period" test too, so if the merge logic ever saw them it
    would glue all four signature entries into one unreadable blob (this is
    exactly the bug that shipped in the first version of this script).
    Keeping the tail out of that pipeline entirely avoids the whole class of
    bug rather than special-casing around it.
    """
    marker = "Executed in duplicate at"
    start = source_text.find(marker)
    if start == -1:
        raise SystemExit(
            f"Could not find {marker!r} in originals/lease.md - has the "
            "execution sentence moved or changed?"
        )
    end_of_sentence = source_text.find(".", start)
    if end_of_sentence == -1:
        raise SystemExit("Execution sentence has no closing period - malformed?")
    return source_text[: end_of_sentence + 1], source_text[end_of_sentence + 1 :]


def parse_signature_labels(signature_source: str) -> list[str]:
    """The role label for each signature line, in order (e.g. "Lessor/Agent",
    "Lessee", "Lessee", "Lessee").

    Each entry in `signature_source` is an underscore line immediately
    followed by its label - a single newline apart, not a blank-line-
    separated paragraph of its own - so splitting on blank lines yields one
    block *per entry*, not one block per line. The underscore run is dropped
    here (it's rendered as a CSS border-top rule instead, see
    `render_signature_lines`); keeping both would double up the line.
    """
    blocks = [b.strip() for b in re.split(r"\n\s*\n", signature_source.strip()) if b.strip()]
    labels = [BLANK.sub("", b).strip() for b in blocks]
    labels = [label for label in labels if label]
    if not labels:
        raise SystemExit(
            "No signature role labels found after the execution sentence in "
            "originals/lease.md - has the signature block moved or changed?"
        )
    return labels


def render_blank(width: str = "short") -> str:
    return f'<span class="blank {width}"></span>'


# Width for each real blank, in the exact order they appear in the document
# (Occupants' blanks are excluded - they're handled separately by
# `spread_occupants_blanks`, always full-width, since each gets its own line
# regardless). Matched by position, not by guessing at nearby keywords: an
# earlier version sized these by sniffing for "Lessor"/"Lessee" in a ~40
# character window around each blank, which reliably picked up the *next*
# sentence's mention of Lessee/Lessor and mis-sized §1 TERM's end-month and
# end-year blanks as "long" instead of a size that fits a month name or a
# 2-digit year. Position is unambiguous where keyword-sniffing wasn't.
BLANK_WIDTHS_IN_ORDER = [
    "medium",  # Lessor.Name
    "medium",  # Lessee.Names
    "medium",  # Premises.Address
    "tiny",    # Term.StartDay
    "word",    # Term.StartMonth
    "tiny",    # Term.StartYear
    "word",    # Term.EndMonth
    "tiny",    # Term.EndYear
    "word",    # Rent.Monthly
    "word",    # Rent.Discounted
    "word",    # Deposit.Amount
    "medium",  # Utilities.Excluded
    "word",    # Execution.City
    "tiny",    # Execution.Day
    "word",    # Execution.Month
    "tiny",    # Execution.Year
]


def markup_blanks(paragraph: str, widths: Iterator[str]) -> str:
    """Turn one paragraph of lease.md text into paragraph-inner HTML: spread
    out the occupants blanks, escape everything, restore the bold section
    labels, then turn each remaining run of underscores into a styled blank
    sized from `widths` - the next entry of `BLANK_WIDTHS_IN_ORDER`, shared
    and advanced across every paragraph in the document so position stays
    correct even though blanks are processed one paragraph at a time.
    """
    spread = spread_occupants_blanks(paragraph)
    spread = mark_parking_radios(spread)
    escaped = html.escape(spread)
    escaped = convert_bold(escaped)

    def choose_width(match: re.Match) -> str:
        width = next(widths, None)
        if width is None:
            raise SystemExit(
                "Found more fill-in blanks than BLANK_WIDTHS_IN_ORDER expects "
                f"(16) - a blank was added to originals/lease.md without "
                "adding a matching entry here."
            )
        return render_blank(width)

    marked = BLANK.sub(choose_width, escaped)
    marked = marked.replace(LINE_BREAK_SENTINEL, "<br>")
    marked = marked.replace(OCCUPANTS_BLANK_SENTINEL, render_blank("long"))
    marked = marked.replace(
        PARKING_LABEL_A_START_SENTINEL,
        '<label class="checkbox-line" id="parking-label-not-available">',
    )
    marked = marked.replace(
        PARKING_RADIO_A_SENTINEL,
        '<input type="radio" name="parking" id="parking-not-available">',
    )
    marked = marked.replace(PARKING_LABEL_A_END_SENTINEL, "</label>")
    marked = marked.replace(
        PARKING_LABEL_B_START_SENTINEL,
        '<label class="checkbox-line" id="parking-label-limited">',
    )
    marked = marked.replace(
        PARKING_RADIO_B_SENTINEL,
        '<input type="radio" name="parking" id="parking-limited">',
    )
    marked = marked.replace(PARKING_LABEL_B_END_SENTINEL, "</label>")
    return marked



def render_signature_lines(labels: list[str]) -> str:
    """One block per signature: a horizontal rule to sign on, the role label
    underneath it - each entry kept visually separate, never run together."""
    rows = "\n".join(
        f'<div class="sig-line">{html.escape(label)}</div>' for label in labels
    )
    return f'<div class="signature-block">\n{rows}\n</div>'


BOLD = re.compile(r"\*\*(.+?)\*\*")


def convert_bold(escaped_text: str) -> str:
    """`**word**` (lease.md's markdown bold) -> `<strong>word</strong>`.

    Must run on already-html-escaped text: `html.escape` leaves literal `*`
    characters untouched, so this is safe to apply afterward, and the
    <strong> tags it inserts are ours, not escaped user content.
    """
    return BOLD.sub(r"<strong>\1</strong>", escaped_text)


OCCUPANTS_BLANKS = re.compile(
    r"(occupied by the following persons only)((?:\s*_{2,})+)"
)

# Sentinels survive html.escape() (which would otherwise mangle a literal
# "<br>" or "<span>") and get swapped for real HTML only after every escaping
# step has already run.
LINE_BREAK_SENTINEL = "\x00BR\x00"
OCCUPANTS_BLANK_SENTINEL = "\x00OCCBLANK\x00"
PARKING_LABEL_A_START_SENTINEL = "\x00PARKINGLABELASTART\x00"
PARKING_LABEL_A_END_SENTINEL = "\x00PARKINGLABELAEND\x00"
PARKING_RADIO_A_SENTINEL = "\x00PARKINGRADIOA\x00"
PARKING_LABEL_B_START_SENTINEL = "\x00PARKINGLABELBSTART\x00"
PARKING_LABEL_B_END_SENTINEL = "\x00PARKINGLABELBEND\x00"
PARKING_RADIO_B_SENTINEL = "\x00PARKINGRADIOB\x00"

# The literal two radio-marked sentences originals/lease.md's PARKING
# section is made of - see mark_parking_radios below.
PARKING_MARKER_A_TEXT = "Parking not available at this address."
PARKING_MARKER_B_TEXT = (
    "Parking spaces are limited to the number of tenants and/or bedrooms, "
    "whichever is less.  Parking spaces are limited to tenant's automobiles "
    "listed on application and in operating condition."
)


def mark_parking_radios(paragraph: str) -> str:
    """PARKING (the lease's last section, by request) gets two real,
    mutually exclusive radio buttons rather than fill-in blanks: picking one
    strikes through the other via JS (see HTML_FOOTER's script) - "not
    available at this address" vs. "available but limited".

    Runs before HTML-escaping, like spread_occupants_blanks - sentinels
    survive escaping untouched and get swapped for real HTML afterward.
    """
    marker_a = f"( ) {PARKING_MARKER_A_TEXT}"
    marker_b = f"( ) {PARKING_MARKER_B_TEXT}"
    if marker_a not in paragraph or marker_b not in paragraph:
        return paragraph
    start_a = paragraph.index(marker_a)
    end_a = start_a + len(marker_a)
    start_b = paragraph.index(marker_b, end_a)
    end_b = start_b + len(marker_b)
    before, between, after = (
        paragraph[:start_a], paragraph[end_a:start_b], paragraph[end_b:],
    )
    return (
        f"{before}"
        f"{PARKING_LABEL_A_START_SENTINEL}{PARKING_RADIO_A_SENTINEL}"
        f"{PARKING_MARKER_A_TEXT}{PARKING_LABEL_A_END_SENTINEL}"
        f"{between}"
        f"{PARKING_LABEL_B_START_SENTINEL}{PARKING_RADIO_B_SENTINEL}"
        f"{PARKING_MARKER_B_TEXT}{PARKING_LABEL_B_END_SENTINEL}"
        f"{after}"
    )


def spread_occupants_blanks(paragraph: str) -> str:
    """The occupant blanks read as a squeezed inline mess if left on the
    same line as the heading text; give each its own full-width writable
    line instead, the way a form meant to be handwritten on actually needs.

    Uses a dedicated sentinel rather than emitting plain underscores: the
    generic `choose_width` context-sniffing in `markup_blanks` only looks
    ~60 characters back from each blank, which is nowhere near enough to
    still see "persons only" once a first 60-underscore blank sits in
    between it and a second one - so leaving these to the generic pass
    would size the first blank right and the rest wrong. Deciding the width
    here, once, is simpler than making the generic heuristic handle it.
    """
    def expand(match: re.Match) -> str:
        blanks = re.findall(r"_{2,}", match.group(2))
        lines = LINE_BREAK_SENTINEL.join(OCCUPANTS_BLANK_SENTINEL for _ in blanks)
        return f"{match.group(1)}{LINE_BREAK_SENTINEL}{lines}"

    return OCCUPANTS_BLANKS.sub(expand, paragraph)


def render_paragraph_tag(block: str, marked_html: str, *, is_preamble: bool) -> str:
    if is_preamble:
        attrs = ' class="preamble"'
    elif STARTS_NEW_SECTION.match(block):
        attrs = ' class="section"'
    else:
        attrs = ""
    return f"<p{attrs}>{marked_html}</p>"


def generate(source_text: str) -> str:
    body_source, signature_source = split_source(source_text)
    body_blocks = extract_body_blocks(body_source)
    labels = parse_signature_labels(signature_source)

    widths = iter(BLANK_WIDTHS_IN_ORDER)
    paragraphs = [
        render_paragraph_tag(block, markup_blanks(block, widths), is_preamble=index == 0)
        for index, block in enumerate(body_blocks)
    ]
    leftover = list(widths)
    if leftover:
        raise SystemExit(
            f"{len(leftover)} width(s) in BLANK_WIDTHS_IN_ORDER were never "
            "used - fewer blanks were found in originals/lease.md than "
            "expected. Has a blank been removed?"
        )
    signature_html = render_signature_lines(labels)

    return (
        HTML_HEAD
        + "\n".join(paragraphs)
        + "\n"
        + signature_html
        + HTML_FOOTER
    )


def main() -> None:
    if not SOURCE.is_file():
        raise SystemExit(f"{SOURCE} does not exist.")
    text = SOURCE.read_text(encoding="utf-8")
    output = generate(text)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(output, encoding="utf-8")
    print(f"Wrote {OUTPUT} from {SOURCE}.")


if __name__ == "__main__":
    main()
