#!/usr/bin/env python3
"""Generate a self-contained, print-ready HTML lease from `documents/lease.md`.

`documents/lease.md` is the only file anyone edits; this script derives the
printable output from it - a blank paper lease meant to be opened in any
browser and printed (Ctrl+P / Cmd+P).

Blanks stay as literal blank lines and the signature lines stay as real
underscore lines: this is meant to be filled in and signed by hand.

Usage:
    python documents/print/generate_print_lease.py

No third-party dependencies: the output is one HTML file with its CSS and
its font inline, so it prints correctly offline, from any browser, on any
machine - nothing to install.
"""
from __future__ import annotations

import base64
import html
import json
import re
from pathlib import Path
from typing import Iterator

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SOURCE = REPO_ROOT / "documents" / "lease.md"
OUTPUT = REPO_ROOT / "documents" / "print" / "lease_print.html"

# The table of apartments a lease can be printed for. Inlined into the output
# (like the font) rather than fetched, so the page stays one self-contained
# file that works offline and from file:// - a fetch would do neither.
#
# Each property's lease_options pick, per group, which version of an
# address-dependent section its lease shows. The other versions are hidden,
# not crossed out - but the section itself, number and title, is on every
# lease, so section numbers are the same for every address. See
# OPTION_GROUPS and the picker script in HTML_FOOTER.
PROPERTIES_FILE = REPO_ROOT / "documents" / "properties.json"
PROPERTIES_MARKER = "__PROPERTIES_JSON__"

# Every lease option group and its versions. Every property must set every
# group to one of these. Walls: A is the standard wording, B plaster.
OPTION_GROUPS = {
    "parking": {"not-available", "limited"},
    "walls": {"A", "B"},
    "yard": {"A", "B"},
}

# The sections holding each group's versions, keyed by their bold title
# rather than their number, since numbers shift when a section is inserted.
# The section itself always shows. Inside it, "(A) ", "(B) " ... begins a
# version, which runs until the next letter or the end of the section - so a
# version can be several paragraphs, bullets included. See
# paragraph_options and mark_versions. PARKING's versions are its two radio
# sentences instead (mark_parking_radios).
SECTION_OPTIONS = {
    "PATIO/YARD": "yard=any",
    "WALLS": "walls=any",
    "PARKING": "parking=any",
}


def load_properties() -> dict:
    """documents/properties.json, checked hard enough that a typo fails the
    build rather than printing a lease with the wrong clauses."""
    if not PROPERTIES_FILE.is_file():
        raise SystemExit(f"{PROPERTIES_FILE} does not exist.")
    data = json.loads(PROPERTIES_FILE.read_text(encoding="utf-8"))
    validate_properties(data)
    return data


def validate_properties(data: dict) -> None:
    properties = data.get("properties")
    if not isinstance(properties, list):
        raise SystemExit("properties.json needs a \"properties\" list.")
    seen_ids: set[str] = set()
    for prop in properties:
        where = f"properties.json entry {prop.get('id')!r}"
        for field in ("id", "address"):
            if not prop.get(field):
                raise SystemExit(f"{where} is missing {field!r}.")
        if prop["id"] in seen_ids:
            raise SystemExit(f"{where}: id is used twice.")
        seen_ids.add(prop["id"])
        # An empty list is a single house: the lease names the address alone.
        units = prop.get("units")
        if not isinstance(units, list):
            raise SystemExit(f"{where}: units must be a list (empty for a single house).")
        if not all(isinstance(u, str) and u for u in units) or len(set(units)) != len(units):
            raise SystemExit(f"{where}: units must be distinct, non-empty strings.")
        options = prop.get("lease_options")
        if not isinstance(options, dict):
            raise SystemExit(f"{where}: lease_options must be an object.")
        for group in options:
            if group not in OPTION_GROUPS:
                raise SystemExit(
                    f"{where}: unknown lease option {group!r} "
                    f"(known: {', '.join(sorted(OPTION_GROUPS))})."
                )
        # Every group, every time: a lease always has each of these sections,
        # so each needs a version to show.
        for group, allowed in OPTION_GROUPS.items():
            if options.get(group) not in allowed:
                raise SystemExit(
                    f"{where}: {group} must be one of {', '.join(sorted(allowed))}, "
                    f"not {options.get(group)!r}."
                )


def properties_json(data: dict) -> str:
    """JSON safe to sit inside a <script> element: a "</" in any value would
    otherwise close the element early."""
    return json.dumps(data, ensure_ascii=False, indent=1).replace("</", "<\\/")

# Gelasio, embedded in the output as base64 rather than linked, so the printed
# lease never depends on which fonts the printing device happens to have.
# Android ships no Georgia at all, and even where Georgia exists an engine can
# substitute; any substitution changes advance widths, which changes line
# breaks, which changes where every page ends. Gelasio is metric-compatible
# with Georgia, so this is the same document, pinned.
# It is a variable font (wght 400-700), and that matters: a static regular
# would leave each browser to synthesize its own bold, and synthesized bold
# differs per engine - reintroducing the variance this exists to remove.
# SIL Open Font License 1.1; the license ships beside it in fonts/OFL.txt.
FONT_FILE = Path(__file__).resolve().parent / "fonts" / "Gelasio-Variable.woff2"

# HTML_HEAD is CSS full of braces, so it cannot be str.format()-ed - the font
# rule is spliced in at this marker instead.
FONT_FACE_MARKER = "  /* @font-face spliced in by font_face_rule() */"

FONT_FACE_TEMPLATE = """  @font-face {
    font-family: "Gelasio";
    font-style: normal;
    /* A range, not one value: a single variable file covers regular to bold. */
    font-weight: 400 700;
    /* block, not swap: a lease that begins printing in a fallback face and
       re-flows mid-print is precisely the bug this is here to prevent. The
       font is a data URI, so nothing is waiting on a network. */
    font-display: block;
    src: url(data:font/woff2;base64,__FONT_DATA__) format("woff2");
  }"""


def font_face_rule() -> str:
    """The @font-face rule with the font file itself inlined as a data URI."""
    if not FONT_FILE.is_file():
        raise SystemExit(
            f"{FONT_FILE} is missing - the printed lease depends on it for "
            "device-independent pagination. Restore it from git."
        )
    encoded = base64.b64encode(FONT_FILE.read_bytes()).decode("ascii")
    return FONT_FACE_TEMPLATE.replace("__FONT_DATA__", encoded)


# A blank line in lease.md is not reliably a real paragraph break (the scanned
# document's page cuts sometimes fall mid-sentence), so a block that doesn't
# end in sentence-final punctuation gets merged into the next one.
SENTENCE_END = re.compile(r'[.!?:]["\')]?$')
STARTS_NEW_SECTION = re.compile(r"^\d+\.\s*\*\*")
BLANK = re.compile(r"_{2,}")

# The company name heads the printed lease. This was a blank line for a
# while, so one form could be shared across every manager in accounts.json -
# printing a name here means this lease is LGD's, and another manager would
# need their own copy. Hardcoded LGD: a 2.0 migration (see CLAUDE.md).
# LLC became Inc on 2026-09-28, at the user's request, and the user set
# this exact form - comma and period - for every document the same day.
COMPANY_NAME = "Lower Garden District Properties, Inc."

TITLE = "Residential Lease"
SUBTITLE = "RESIDENTIAL LEASE"
# This document's own CSS on top of HTML_HEAD's - none; the other
# generators each have one, and the combined page gathers them.
EXTRA_CSS = ""

# HTML_HEAD and PICKER_FOOTER are shared with the security deposit's
# generator, which fills the same placeholders with its own values - see
# render_head and render_picker_footer.
HTML_HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="/favicon.ico">
<title>__TITLE__</title>
<style>
  /* @font-face spliced in by font_face_rule() */
  @page {
    size: letter;
    margin: 0.85in;
    @top-center {
      content: "__COMPANY__ — Page " counter(page)
               " of " counter(pages);
      font-family: "Gelasio", Georgia, "Times New Roman", Times, serif;
      font-size: 9pt;
      color: #444;
    }
    @bottom-center {
      content: "__COMPANY__ — Page " counter(page)
               " of " counter(pages);
      font-family: "Gelasio", Georgia, "Times New Roman", Times, serif;
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
    font-family: "Gelasio", Georgia, "Times New Roman", Times, serif;
    font-size: 11.5pt;
    line-height: 1.4;
    max-width: 7.5in;
    margin: 0 auto;
    padding: 0.25in 0 1in;
  }
  h1.company {
    text-align: center;
    font-size: 13pt;
    font-weight: bold;
    letter-spacing: 0.03em;
    margin: 0 0 0.04in;
  }
  p.subtitle {
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
    break-after: avoid;
  }
  p.bullet {
    /* A list item written in lease.md as its own "• " paragraph: hanging
       indent so wrapped lines align with the text, not the bullet. */
    margin: 0 0 0.4em 1.2em;
    text-indent: -0.9em;
    text-align: left;
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
  /* A version that does not apply to the chosen apartment. Several rules
     here set display (the picker is flex), so one override covers them. */
  [hidden] { display: none !important; }
  /* On a blank lease, the PARKING radio not picked by hand. */
  .struck {
    text-decoration: line-through;
    color: #555;
  }
  /* Keeps the blank's own min-width: a filled-in address takes the same
     space as the empty blank, so every address paginates identically. */
  .blank.filled {
    border-bottom: none;
    font-weight: bold;
    text-decoration: underline;
  }
  /* The apartment picker is screen-only: it never reaches paper. It sets no
     font-family of its own, so it inherits Gelasio from body. */
  .picker {
    position: fixed;
    inset: 0;
    z-index: 10;
    display: flex;
    /* Centred by the box's auto margins rather than align-items, so a
       popup taller than a phone screen scrolls from its top instead of
       being cut off above it. */
    overflow-y: auto;
    padding: 16px 16px 80px;
    /* Opaque, not a dimmed overlay: the lease is not shown at all until an
       apartment is picked, so nobody reads or prints the wrong one. */
    background: #e9e7e2;
  }
  .picker[hidden] { display: none; }
  .picker-box {
    margin: auto;
    width: 100%;
    max-width: 380px;
    padding: 22px 24px;
    border-radius: 8px;
    background: #fff;
    box-shadow: 0 4px 18px rgba(0, 0, 0, .15);
  }
  .picker-box h2 { margin: 0 0 14px; font-size: 14pt; }
  .picker-box label { display: block; margin: 0 0 12px; font-size: 11pt; }
  .picker-box label[hidden] { display: none; }
  .picker-box .optional { color: #777; font-size: 9.5pt; }
  .picker-box select, .picker-box input[type=text] {
    display: block;
    box-sizing: border-box;
    width: 100%;
    margin-top: 4px;
    padding: 6px;
    font: inherit;
    /* 16px or more, or an iPhone zooms the page in on tapping a box. */
    font-size: max(16px, 1em);
  }
  .picker-summary {
    margin: 4px 0 0;
    padding-left: 1.2em;
    font-size: 10.5pt;
    color: #333;
  }
  .picker-summary li { margin-bottom: 2px; }
  /* A term: the number box and its months/years select on one line. */
  .term-row { display: flex; gap: 8px; margin-top: 4px; }
  .term-row input[data-term], .term-row select { margin-top: 0; }
  .picker-box .term-row input[data-term] { width: 6em; flex: 0 0 auto; }
  .picker-box .term-row select { width: auto; flex: 0 0 auto; }
  /* The combined page's document checkboxes. */
  .doc-choices { border: 0; margin: 0 0 14px; padding: 0; }
  .doc-choices legend { padding: 0; margin-bottom: 6px; font-size: 11pt; font-weight: bold; }
  .picker-box label.doc-choice { display: flex; align-items: center; gap: 0.5em; margin: 0 0 6px; }
  .picker-actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 16px; }
  .picker-actions button {
    padding: 8px 14px;
    border: 1px solid #1f5d4c;
    border-radius: 6px;
    background: #1f5d4c;
    color: #fff;
    font: inherit;
    cursor: pointer;
  }
  .picker-actions button.secondary, .picker-actions a.secondary { background: transparent; color: #1f5d4c; }
  /* Back sits in the popup while it is open (the floating one would cover
     these buttons on a short screen), and floats once it closes. */
  .picker-actions a {
    padding: 8px 14px;
    border: 1px solid #1f5d4c;
    border-radius: 6px;
    text-decoration: none;
    font: inherit;
  }
  .picker-actions button:disabled { opacity: .45; cursor: not-allowed; }
  /* Screen-only, like the picker: a Print button that floats over the
     document while it is read on screen, so "View" is one click from
     paper. Hidden until the picker is done, so it never offers to print
     a lease before its apartment is chosen. */
  .float-buttons {
    position: fixed;
    right: 16px;
    bottom: 16px;
    z-index: 20;
    display: flex;
    gap: 10px;
  }
  .float-buttons a, .float-buttons button {
    padding: 10px 20px;
    border: 1px solid #1f5d4c;
    border-radius: 999px;
    background: #1f5d4c;
    color: #fff;
    font: inherit;
    font-size: 12pt;
    box-shadow: 0 3px 12px rgba(0, 0, 0, .25);
    cursor: pointer;
  }
  .float-buttons a { text-decoration: none; background: #fff; color: #1f5d4c; }
  .float-buttons button:hover { background: #174a3c; }
  /* Three of them fit a small phone without covering most of the page. */
  @media screen and (max-width: 420px) {
    .float-buttons { right: 10px; bottom: 10px; gap: 8px; }
    .float-buttons a, .float-buttons button { padding: 7px 14px; font-size: 11pt; }
  }
  .execution-block {
    /* "Executed in duplicate at ___ this ___ day of ___" and the four
       signature lines are one unit: those signatures execute that sentence.
       A break between them leaves a bare signature page - odd to read, and
       poor practice on a document that gets signed.
       This is a relative constraint, not a fixed position, which is why it
       survives a different paper size, different margins or a different
       font - the things that actually vary between a desktop and a phone. */
    page-break-inside: avoid;
    break-inside: avoid;
  }
  .signature-block {
    /* Both spellings: page-break-* is what older WebKit honours, break-* is
       the current spec. They are not reliably aliased to each other. */
    page-break-inside: avoid;
    break-inside: avoid;
    page-break-before: avoid;
    break-before: avoid;
    margin-top: 0.3in;
  }
  .sig-line {
    /* A single signature line must never be split across a page boundary,
       whatever happens to the block as a whole. */
    page-break-inside: avoid;
    break-inside: avoid;
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
    .picker { display: none !important; }
    .float-buttons { display: none !important; }
    a { color: inherit; text-decoration: none; }
    /* Pin the printed column to the paper, in absolute units.
       A phone lays the screen out about 390px wide, and mobile browsers
       print from that layout instead of reflowing to paper width - which
       is why this came out 9 pages from a phone and 6 from a desktop
       (measured: forcing a 390px column reproduces 9 exactly).
       "width: auto" does not fix that, because auto still resolves
       against whatever narrow box the browser used. An absolute width
       does not: 6.8in is Letter's 8.5in less the 0.85in @page margins on
       each side, so the column is identical on every device. */
    body {
      width: 6.8in;
      max-width: 6.8in;
      margin: 0 auto;
      padding: 0 0 0.25in;
    }
  }
  /* The combined page: each later document starts a new sheet of paper,
     the break sitting on its heading (see the wrapper rules in print). */
  section.document:not([hidden]) ~ section.document:not([hidden]) > h1.company {
    page-break-before: always;
    break-before: page;
  }
  @media print {
    /* The wrappers take no part in printed layout, so every document
       paginates exactly as it did before they existed. (A real box around
       the lease made Chrome break its pages differently.) The screen
       zoom must not reach paper either. */
    .sheet, .sheet-stack, section.document { display: contents; zoom: 1 !important; }
  }
  /* On screen a document is shown as the sheet of Letter paper it prints
     on: 8.5in wide, the same 0.85in margins, so every line breaks where
     it will on paper. A script zooms each sheet down to fit a narrower
     screen (fitSheets), so a phone shows the page, not a reflow of it. */
  @media screen {
    html, body { background: #e9e7e2; }
    body { max-width: none; padding: 12px 0 88px; }
    .sheet {
      display: block;
      box-sizing: border-box;
      width: 8.5in;
      min-height: 11in;
      margin: 0 auto;
      padding: 0.85in;
      background: #fff;
      box-shadow: 0 1px 8px rgba(0, 0, 0, .18);
    }
    .sheet:not([hidden]) ~ .sheet:not([hidden]) { margin-top: 12px; }
    .sheet-stack > .footer-note { max-width: 6.8in; margin: 0.3in auto 0; border: 0; }
    .footer-note code { overflow-wrap: anywhere; }
  }
</style>
</head>
<body>
"""

# The heading every document opens with. Kept apart from HTML_HEAD because
# the combined page (generate_print_packet.py) prints one per document.
TITLE_BLOCK = """<h1 class="company">__COMPANY__</h1>
<p class="subtitle">__SUBTITLE__</p>
"""


def render_title_block(company: str, subtitle: str) -> str:
    return (TITLE_BLOCK.replace("__COMPANY__", html.escape(company))
            .replace("__SUBTITLE__", html.escape(subtitle)))


def render_page_head(company: str, title: str) -> str:
    """HTML_HEAD with its placeholders filled and the font spliced in -
    everything up to and including <body>, with no document heading."""
    return (HTML_HEAD.replace(FONT_FACE_MARKER, font_face_rule())
            .replace("__COMPANY__", html.escape(company))
            .replace("__TITLE__", html.escape(title)))


def render_head(company: str, title: str, subtitle: str) -> str:
    """The page head, the sheet the document sits on, and its heading: one
    document's page. DOC_BUTTONS closes the sheet."""
    return (render_page_head(company, title) + '<main class="sheet">\n'
            + render_title_block(company, subtitle))


LEASE_FOOTER_NOTE = """
<div class="footer-note">
  This is a blank lease generated from <code>documents/lease.md</code> by
  <code>documents/print/generate_print_lease.py</code> for printing and hand-filling on
  paper. It will not appear on a printed copy (hidden in print styles).
  Regenerate after editing <code>documents/lease.md</code>. The "Page X of Y"
  line at the top and bottom of each page is a CSS page-number counter: it
  renders correctly when printed from Chrome, Edge, or Safari (18.2+), but not
  from Firefox, which does not yet support this CSS feature as of early 2026 -
  if you print from Firefox, those lines will simply be missing rather than
  wrong.
</div>"""

# Floating Back and Print buttons, shared by every printable document,
# with the script that fits each sheet to the screen. It also closes the
# <main> that render_head opens, so the popup and the buttons are never
# zoomed with the page. Screen only.
#
# Back returns to the page that opened this one - everything opens in the
# same tab - or, opened directly, to the manager page. Print waits for the
# embedded font, for the same reason the auto-print does; documents with a
# popup show it once the popup closes.
DOC_BUTTONS = """
</main>
<div class="float-buttons">
  <a href="../../" id="home-button">Home</a>
  <a href="../../manager/" id="back-button">Back</a>
  <button type="button" id="print-button" hidden>Print</button>
</div>
<script>
  document.getElementById("print-button").addEventListener("click", function () {
    var fontsReady = (document.fonts && document.fonts.ready) ? document.fonts.ready : Promise.resolve();
    fontsReady.then(function () { window.print(); });
  });
  document.getElementById("back-button").addEventListener("click", function (event) {
    var cameFromHere = false;
    try { cameFromHere = new URL(document.referrer).origin === window.location.origin; } catch (e) {}
    if (cameFromHere && window.history.length > 1) {
      event.preventDefault();
      window.history.back();
    }
  });
  // Zoom each sheet down to the screen's width, never up. Zoom rather
  // than a narrower column: the lines must break where they do on paper.
  function fitSheets() {
    var room = document.documentElement.clientWidth - 16;
    document.querySelectorAll(".sheet").forEach(function (sheet) {
      sheet.style.zoom = "";
      var width = sheet.offsetWidth;
      if (width > room) { sheet.style.zoom = String(room / width); }
    });
  }
  fitSheets();
  window.addEventListener("resize", fitSheets);
</script>"""

PICKER_FOOTER = """
<div class="picker" id="picker" role="dialog" aria-modal="true" aria-labelledby="picker-title">
  <form class="picker-box" id="picker-form">
    <h2 id="picker-title">__QUESTION__</h2>
__DOC_CHOICES__
    <label>Address
      <select id="picker-property"></select>
    </label>
    <label>Unit
      <select id="picker-unit"></select>
    </label>
__EXTRA_FIELDS__
    <ul class="picker-summary" id="picker-summary" aria-live="polite"></ul>
    <div class="picker-actions">
      <button type="submit" id="picker-fill">Fill in this apartment</button>
      <button type="button" class="secondary" id="picker-blank">Leave it blank</button>
      <a class="secondary" id="picker-home" href="../../">Home</a>
      <a class="secondary" id="picker-back" href="../../manager/">Back</a>
    </div>
  </form>
</div>
<script type="application/json" id="lease-properties">
__PROPERTIES_JSON__
</script>
<script>
  // Before anything prints, the manager picks the apartment this lease is
  // for (from documents/properties.json, inlined above). That fills in the
  // premises line and, in each address-dependent section, hides every
  // version that does not apply. The sections themselves - number and
  // title - always show, so section numbers are the same on every lease.
  // "Leave it blank" prints every version, labelled, as a blank form.
  var properties = JSON.parse(document.getElementById("lease-properties").textContent).properties;
  var baseTitle = document.title;
  var picker = document.getElementById("picker");
  var propertySelect = document.getElementById("picker-property");
  var unitSelect = document.getElementById("picker-unit");

  var pageLoaded = new Promise(function (resolve) {
    window.addEventListener("load", resolve);
  });

  function optionParts(element) {
    var parts = element.getAttribute("data-option").split("=");
    return { group: parts[0], value: parts[1] };
  }

  function chosenProperty() {
    return properties[Number(propertySelect.value)];
  }

  // One line per address-dependent setting, so the manager can see what
  // this lease will say before printing it.
  var SUMMARY = {
    parking: { "limited": "Parking (limited spaces)", "not-available": "No parking" },
    walls: { A: "No plaster (standard walls)", B: "Plaster walls" },
    yard: { A: "Yard A: Lessee maintains patio/yard and alley",
            B: "Yard B: Lessor maintains all" }
  };

  function showUnits() {
    var property = chosenProperty();
    unitSelect.length = 0;
    property.units.forEach(function (unit) { unitSelect.add(new Option(unit, unit)); });
    unitSelect.parentNode.hidden = property.units.length === 0;
    var summary = document.getElementById("picker-summary");
    summary.textContent = "";
    ["parking", "walls", "yard"].forEach(function (group) {
      var item = document.createElement("li");
      item.textContent = SUMMARY[group][property.lease_options[group]];
      summary.appendChild(item);
    });
  }

  function applyProperty(property, unit) {
    var place = property.units.length ? property.address + ", Unit " + unit : property.address;
    // An id on a one-document page; data-premises on the combined page,
    // where each document has its own premises blank.
    document.querySelectorAll("#premises, [data-premises]").forEach(function (premises) {
      premises.textContent = place;
      premises.classList.add("filled");
    });
    document.title = baseTitle + " - " + place;
    document.querySelectorAll("[data-option]").forEach(function (element) {
      var option = optionParts(element);
      if (option.value === "any") { return; }  // the section itself always shows
      var applies = option.value === property.lease_options[option.group];
      element.hidden = !applies;
      // A parking sentence reads as plain text once it is the only one.
      var radio = element.querySelector("input[type=radio]");
      if (radio) { radio.checked = applies; radio.hidden = true; }
    });
    document.querySelectorAll(".version-label").forEach(function (label) {
      label.hidden = true;
    });
  }

  // Opening this page (from the dashboard's "Print paper lease" button) is
  // the whole point of the page, so once an apartment is picked, bring up
  // the browser's print dialog rather than making the manager find Ctrl+P.
  //
  // Wait for the embedded font before opening it. "load" can fire while the
  // document is still laid out in a fallback face, and printing at that
  // moment paginates on the wrong advance widths - the exact class of bug
  // this page keeps regressing into. The small delay after that lets layout
  // settle so the preview is right.
  //
  // The dashboard's "View paper lease" button opens this page with #view,
  // which skips the dialog so the lease can just be read on screen.
  // Money boxes: only digits, "$" and "." - and always exactly one "$",
  // at the front, supplied rather than typed. Anything else typed or
  // pasted is dropped, and extra "$" signs collapse into the one.
  document.querySelectorAll("input[data-money]").forEach(function (input) {
    function clean() {
      var before = input.value;
      var caret = input.selectionStart === null ? before.length : input.selectionStart;
      var amount = before.replace(/[^0-9.]/g, "");
      var cleaned = "$" + amount;
      if (cleaned === before) { return; }
      // Keep the caret after the same digits it followed.
      var kept = before.slice(0, caret).replace(/[^0-9.]/g, "").length;
      input.value = cleaned;
      input.setSelectionRange(kept + 1, kept + 1);
    }
    input.addEventListener("input", clean);
    clean();
  });

  // Term boxes: a whole number only; months or years is the select beside it.
  document.querySelectorAll("input[data-term]").forEach(function (input) {
    input.addEventListener("input", function () {
      var digits = input.value.replace(/[^0-9]/g, "").replace(/^0+/, "");
      if (digits !== input.value) { input.value = digits; }
    });
  });

  // The combined page's document checkboxes: an unticked document is
  // hidden, and so is any popup question only it asks. A page of one
  // document has no checkboxes, and this does nothing.
  var docChoices = document.querySelectorAll("input[data-doc-choice]");
  function chosenDocs() {
    var chosen = {};
    docChoices.forEach(function (box) { if (box.checked) { chosen[box.value] = true; } });
    return chosen;
  }
  function showQuestions() {
    var chosen = chosenDocs();
    document.querySelectorAll(".picker-box [data-for-docs]").forEach(function (question) {
      question.hidden = !question.getAttribute("data-for-docs").split(" ").some(function (doc) {
        return chosen[doc];
      });
    });
    var none = docChoices.length > 0 && Object.keys(chosen).length === 0;
    document.getElementById("picker-fill").disabled = none || !properties.length;
    document.getElementById("picker-blank").disabled = none;
  }
  function showDocs() {
    if (!docChoices.length) { return; }
    var chosen = chosenDocs();
    document.querySelectorAll("section.document").forEach(function (section) {
      section.hidden = !chosen[section.getAttribute("data-doc")];
    });
  }
  // The manager page picks the documents: ?docs=lease,deposit. They were
  // chosen there, so the popup does not ask again - it hides its own
  // checkboxes and asks only about the apartment, naming the documents.
  var preset = new URLSearchParams(window.location.search).get("docs");
  if (preset !== null && docChoices.length) {
    var wanted = preset.split(",");
    var names = [];
    docChoices.forEach(function (box) {
      box.checked = wanted.indexOf(box.value) !== -1;
      if (box.checked) { names.push(box.getAttribute("data-name")); }
    });
    if (names.length) {
      document.querySelector(".doc-choices").hidden = true;
      var list = names.length === 1 ? names[0]
        : names.slice(0, -1).join(", ") + " and " + names[names.length - 1];
      document.getElementById("picker-title").textContent = names.length === 1
        ? "Which apartment is this " + list + " for?"
        : "Which apartment are the " + list + " for?";
      baseTitle = list.charAt(0).toUpperCase() + list.slice(1);
      document.title = baseTitle;
    }
  }
  docChoices.forEach(function (box) { box.addEventListener("change", showQuestions); });
  showQuestions();

  // Home and Back sit in the popup while it is open - floating, they would
  // cover the popup's own buttons on a short screen - and float once it
  // closes. The popup's Back just clicks the floating one, so both behave
  // the same.
  var floatingBack = document.getElementById("back-button");
  var floatingHome = document.getElementById("home-button");
  floatingBack.hidden = true;
  floatingHome.hidden = true;
  document.getElementById("picker-back").addEventListener("click", function (event) {
    event.preventDefault();
    floatingBack.click();
  });

  function finish() {
    showDocs();
    picker.hidden = true;
    floatingBack.hidden = false;
    floatingHome.hidden = false;
    document.getElementById("print-button").hidden = false;
    if (window.location.hash === "#view") { return; }
    pageLoaded.then(function () {
      var fontsReady = (document.fonts && document.fonts.ready)
        ? document.fonts.ready
        : Promise.resolve();
      return fontsReady;
    }).then(function () {
      setTimeout(function () { window.print(); }, 150);
    });
  }

  properties.forEach(function (property, index) {
    propertySelect.add(new Option(property.address, String(index)));
  });
  if (properties.length) {
    showUnits();
  } else {
    document.getElementById("picker-fill").disabled = true;
  }
  showQuestions();
  propertySelect.addEventListener("change", showUnits);
  document.getElementById("picker-form").addEventListener("submit", function (event) {
    event.preventDefault();
    // Parking, walls and yard all come from documents/properties.json.
    applyProperty(chosenProperty(), unitSelect.value);
    // Optional boxes (a document's own, e.g. the application's rent): each
    // fills the blank it names; left empty, the blank stays to write in.
    document.querySelectorAll("input[data-fills]").forEach(function (input) {
      if (input.closest("[hidden]")) { return; }  // a document not chosen
      var target = document.getElementById(input.getAttribute("data-fills"));
      var value = input.value.trim();
      // An amount's printed label already ends in "$"; "$" alone is empty.
      if (input.hasAttribute("data-money")) { value = value.replace(/^[$]/, ""); }
      // A term is a number of months or of years: "1 year", "12 months".
      if (input.hasAttribute("data-term") && value) {
        var unit = document.getElementById(input.id + "-unit").value;
        value = value + " " + unit + (value === "1" ? "" : "s");
      }
      if (target && value) {
        target.textContent = value;
        target.classList.add("filled");
      }
    });
    finish();
  });
  document.getElementById("picker-blank").addEventListener("click", finish);

  // On a blank lease the PARKING radio buttons work by hand: picking one
  // crosses out the other. (The security deposit shares this script and
  // has no parking section, hence the check.)
  var notAvailable = document.getElementById("parking-not-available");
  var limited = document.getElementById("parking-limited");
  function updateParkingStrikes() {
    document.getElementById("parking-label-not-available").classList.toggle("struck", limited.checked);
    document.getElementById("parking-label-limited").classList.toggle("struck", notAvailable.checked);
  }
  if (notAvailable && limited) {
    notAvailable.addEventListener("change", updateParkingStrikes);
    limited.addEventListener("change", updateParkingStrikes);
  }

</script>
</body>
</html>
"""


def render_picker_footer(document_name: str, fields: tuple[tuple, ...] = (),
                         documents: tuple[tuple[str, str, bool], ...] = (),
                         money: tuple[str, ...] = (), terms: tuple[str, ...] = ()) -> str:
    """The apartment picker, its script and the inlined apartment table -
    shared by every printable document that names the premises.

    `fields` adds optional text boxes to the popup, as (label, blank id)
    pairs, or (label, blank id, doc key) when the combined page asks it
    only for that document: whatever is typed fills the element with that
    id. `documents`, on the combined page only, is (key, name, ticked) per
    document, offered as checkboxes above the apartment questions. The
    blank ids in `money` are amounts: their boxes take only digits, "$"
    and ".", and always start with one "$". The blank ids in `terms` are
    lengths of time: a whole number and a choice of months or years, never
    both, filled as "12 months" or "1 year"."""
    lines = []
    for field in fields:
        label, target = field[0], field[1]
        for_docs = f' data-for-docs="{html.escape(field[2])}"' if len(field) > 2 else ""
        lines.append(
            f'    <label{for_docs}>{html.escape(label)} <span class="optional">(optional)</span>'
            + ('\n      <span class="term-row">' if target in terms else "")
            + f'\n      <input type="text" id="picker-{html.escape(target)}" data-fills="{html.escape(target)}"'
            + (' data-money inputmode="decimal" value="$"' if target in money else "")
            + (' data-term inputmode="numeric"' if target in terms else "")
            + '>'
            + (f'\n      <select id="picker-{html.escape(target)}-unit" aria-label="Months or years">'
               '<option value="month">months</option><option value="year">years</option></select>'
               '</span>' if target in terms else "")
            + '\n'
            f"    </label>")
    extra = "\n".join(lines)
    if documents:
        boxes = "\n".join(
            f'      <label class="doc-choice"><input type="checkbox" data-doc-choice value="{html.escape(key)}"'
            f' data-name="{html.escape(name.lower())}"'
            f'{" checked" if ticked else ""}> {html.escape(name)}</label>'
            for key, name, ticked in documents)
        choices = f'    <fieldset class="doc-choices">\n      <legend>Documents</legend>\n{boxes}\n    </fieldset>'
        question = "Which documents, and for which apartment?"
    else:
        choices = ""
        question = f"Which apartment is this {document_name} for?"
    return DOC_BUTTONS + (PICKER_FOOTER.replace("__QUESTION__", html.escape(question))
            .replace("__DOC_CHOICES__", choices)
            .replace("__EXTRA_FIELDS__", extra)
            .replace(PROPERTIES_MARKER, properties_json(load_properties())))

def flatten_paragraph(text: str) -> str:
    return re.sub(r"[ \t]*\n[ \t]*", " ", text).strip()


def extract_body_blocks(source_text: str) -> list[str]:
    """See SENTENCE_END above for why blocks get merged."""
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
            f"Could not find {marker!r} in documents/lease.md - has the "
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
            "documents/lease.md - has the signature block moved or changed?"
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
                f"({len(BLANK_WIDTHS_IN_ORDER)}) - a blank was added to documents/lease.md without "
                "adding a matching entry here."
            )
        return render_blank(width)

    marked = BLANK.sub(choose_width, escaped)
    marked = marked.replace(LINE_BREAK_SENTINEL, "<br>")
    marked = marked.replace(OCCUPANTS_BLANK_SENTINEL, render_blank("long"))
    marked = marked.replace(
        PARKING_LABEL_A_START_SENTINEL,
        '<label class="checkbox-line" id="parking-label-not-available"'
        ' data-option="parking=not-available">',
    )
    marked = marked.replace(
        PARKING_RADIO_A_SENTINEL,
        '<input type="radio" name="parking" id="parking-not-available">',
    )
    marked = marked.replace(PARKING_LABEL_A_END_SENTINEL, "</label>")
    marked = marked.replace(
        PARKING_LABEL_B_START_SENTINEL,
        '<label class="checkbox-line" id="parking-label-limited"'
        ' data-option="parking=limited">',
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

# The literal two radio-marked sentences documents/lease.md's PARKING
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


SECTION_TITLE = re.compile(r"^\d+\.\s*\*\*(.+?)\*\*")


def section_option(block: str) -> str | None:
    """The data-option tag for a whole section that is one lease option
    (see SECTION_OPTIONS), or None."""
    title = SECTION_TITLE.match(block)
    return SECTION_OPTIONS.get(title.group(1)) if title else None


VERSION_START = re.compile(r"^\(([A-Z])\) ")
HEADING_VERSION = re.compile(r"^\d+\.\s*\*\*.+?\*\*\s*\(([A-Z])\) ")


def paragraph_options(blocks: list[str]) -> list[str | None]:
    """The data-option tag for each body paragraph.

    A version-holding section's heading paragraph is tagged "group=any" -
    it always shows (a "(A) " version inside it is wrapped separately, by
    mark_versions). Every later paragraph of the section belongs to the
    version most recently started with "(A) ", "(B) " ..., so a version can
    run over several paragraphs. The preamble comes before any section and
    the execution sentence closes the lease, so neither is ever tagged."""
    options: list[str | None] = []
    current = None
    version = None
    for index, block in enumerate(blocks):
        if STARTS_NEW_SECTION.match(block):
            current = section_option(block)
            heading = HEADING_VERSION.match(block)
            version = heading.group(1) if heading else None
            tag = current
        elif current and current.endswith("=any"):
            start = VERSION_START.match(block)
            if start:
                version = start.group(1)
            group = current.split("=")[0]
            tag = f"{group}={version}" if version else current
        else:
            tag = current
        in_a_section = 0 < index < len(blocks) - 1
        options.append(tag if in_a_section else None)
    return options


def render_paragraph_tag(block: str, marked_html: str, *, is_preamble: bool,
                         option: str | None = None) -> str:
    tag = f' data-option="{option}"' if option else ""
    if is_preamble:
        attrs = ' class="preamble"'
    elif STARTS_NEW_SECTION.match(block):
        attrs = f'{tag} class="section"'
    elif block.startswith("• "):
        attrs = f'{tag} class="bullet"'
    else:
        attrs = tag
    return f"<p{attrs}>{marked_html}</p>"


# The premises blank is the one the apartment picker fills in.
PREMISES_BLANK = 'the premises known as <span class="blank medium"></span>'
PREMISES_BLANK_WITH_ID = 'the premises known as <span class="blank medium" id="premises"></span>'


HEADING_VERSION_HTML = re.compile(r"\(([A-Z])\) (.*)</p>$")
VERSION_LABEL_HTML = re.compile(r"^(<p[^>]*>)\(([A-Z])\) ")


def version_label(letter: str) -> str:
    # The "(A) " label only means something on a blank lease, where every
    # version shows; for a chosen apartment the script hides it.
    return f'<span class="version-label">({letter}) </span>'


def mark_versions(paragraph: str, option: str | None) -> str:
    """Wrap a version's "(A) " label so it can be hidden, and - in a
    section's heading paragraph, tagged "group=any" - wrap the version's
    text in a span tagged "group=A", so it can be hidden without hiding the
    section number and title. PARKING's "( )" radios never match: a letter
    is required."""
    if not option:
        return paragraph
    if option.endswith("=any"):
        group = option.split("=")[0]
        return HEADING_VERSION_HTML.sub(
            lambda m: (f'<span data-option="{group}={m.group(1)}">'
                       f'{version_label(m.group(1))}{m.group(2)}</span></p>'),
            paragraph,
            count=1,
        )
    return VERSION_LABEL_HTML.sub(lambda m: m.group(1) + version_label(m.group(2)),
                                  paragraph, count=1)


def check_option_wording(paragraphs: list[str]) -> None:
    """Every value OPTION_GROUPS says has wording must actually be tagged
    somewhere in the lease - otherwise it would silently never show or hide."""
    body = "\n".join(paragraphs)
    for group, values in OPTION_GROUPS.items():
        for value in sorted(values):
            if f'data-option="{group}={value}"' not in body:
                raise SystemExit(
                    f"OPTION_GROUPS says {group}={value} has wording, but nothing in "
                    "documents/lease.md is tagged with it. Has its text moved or changed?"
                )


def check_section_options(paragraphs: list[str]) -> None:
    """Every SECTION_OPTIONS title must still name a real section - a
    renamed one would otherwise quietly stop being crossed out."""
    for title, option in SECTION_OPTIONS.items():
        if not any(f'data-option="{option}"' in p for p in paragraphs):
            raise SystemExit(
                f"No section titled {title!r} in documents/lease.md, so it "
                f"cannot be tagged {option!r}. Has it been renamed?"
            )


def render_body(source_text: str) -> str:
    """The lease itself, without the page around it - shared by this page
    and the combined one (generate_print_packet.py)."""
    body_source, signature_source = split_source(source_text)
    body_blocks = extract_body_blocks(body_source)
    labels = parse_signature_labels(signature_source)

    widths = iter(BLANK_WIDTHS_IN_ORDER)
    options = paragraph_options(body_blocks)
    paragraphs = [
        mark_versions(
            render_paragraph_tag(block, markup_blanks(block, widths), is_preamble=index == 0,
                                 option=options[index]),
            options[index],
        )
        for index, block in enumerate(body_blocks)
    ]
    leftover = list(widths)
    if leftover:
        raise SystemExit(
            f"{len(leftover)} width(s) in BLANK_WIDTHS_IN_ORDER were never "
            "used - fewer blanks were found in documents/lease.md than "
            "expected. Has a blank been removed?"
        )
    if PREMISES_BLANK not in paragraphs[0]:
        raise SystemExit(
            "Could not find the premises blank in the lease's opening "
            "paragraph, so the apartment picker has nothing to fill in."
        )
    paragraphs[0] = paragraphs[0].replace(PREMISES_BLANK, PREMISES_BLANK_WITH_ID)
    check_section_options(paragraphs)
    check_option_wording(paragraphs)
    signature_html = render_signature_lines(labels)

    # The execution sentence is the last body paragraph, and it belongs with
    # the signature lines - see .execution-block in the CSS for why.
    if "Executed in duplicate at" not in paragraphs[-1]:
        raise SystemExit(
            "The last body paragraph is no longer the execution sentence, so "
            "it cannot be bound to the signature lines. Has the tail of "
            "documents/lease.md moved?"
        )
    tail_html = (
        '<div class="execution-block">\n'
        + paragraphs[-1]
        + "\n"
        + signature_html
        + "\n</div>"
    )

    return "\n".join(paragraphs[:-1]) + "\n" + tail_html


def generate(source_text: str) -> str:
    return (
        render_head(COMPANY_NAME, TITLE, SUBTITLE)
        + render_body(source_text)
        + LEASE_FOOTER_NOTE
        + render_picker_footer("lease")
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
