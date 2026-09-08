"""Tests for print/generate_print_lease.py.

These guard the three real bugs found while building this generator:
1. Markdown "**bold**" rendered as literal asterisks instead of <strong>.
2. All four signature lines were merged into one unreadable blob, because
   a bare blank line and a label like "Lessor/Agent" both lack the
   sentence-final punctuation the shared merge logic uses as its signal to
   stop combining blocks - nothing stopped it from eating the whole tail.
3. The occupant blanks and the very first (Lessor name) blank were sized
   too small because the context window used to guess a sensible blank
   width didn't reach far enough to see the nearby keyword.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parent.parent / "print" / "generate_print_lease.py"
SOURCE_PATH = Path(__file__).resolve().parent.parent / "originals" / "lease.md"


def _load_module():
    spec = importlib.util.spec_from_file_location("generate_print_lease", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gen():
    return _load_module()


@pytest.fixture(scope="module")
def real_output(gen) -> str:
    return gen.generate(SOURCE_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Bug 1: bold markdown must become real HTML, not literal asterisks
# ---------------------------------------------------------------------------

def test_no_literal_markdown_asterisks_survive(real_output):
    assert "**" not in real_output


def test_section_labels_are_rendered_bold(real_output):
    assert "<strong>TERM</strong>" in real_output
    assert "<strong>SMOKING</strong>" in real_output
    assert "<strong>OTHER</strong>" in real_output


# ---------------------------------------------------------------------------
# Bug 2: every signature line must stay a separate, legible entry
# ---------------------------------------------------------------------------

def test_signature_block_has_four_separate_entries(real_output):
    assert real_output.count('<div class="sig-line">') == 4


def test_signature_labels_are_not_merged_together(real_output):
    """The actual bug: all four entries ended up concatenated into one
    div, e.g. "_____ Lessor/Agent _____ Lessee _____ Lessee _____ Lessee"."""
    signature_area = real_output[real_output.index('<div class="signature-block">') :]
    assert "Lessor/Agent" in signature_area
    assert signature_area.count("Lessee") == 3
    # None of the four lines should contain more than one role label.
    import re

    for line in re.findall(r'<div class="sig-line">([^<]*)</div>', signature_area):
        assert line.count("Lessor") + line.count("Lessee") == 1, line


def test_signature_lines_carry_no_literal_underscores(real_output):
    """The underscore rule is CSS (border-top); the text content should be
    just the role label, not the underscore run duplicated as text too."""
    signature_area = real_output[real_output.index('<div class="signature-block">') :]
    for line in signature_area.split('<div class="sig-line">')[1:]:
        label = line.split("</div>")[0]
        assert "_" not in label


# ---------------------------------------------------------------------------
# Bug 3: blanks that matter must be wide enough to write in
# ---------------------------------------------------------------------------

def test_the_lessor_name_blank_is_wide_enough_to_write_a_name_in(real_output):
    """The very first blank in the document - where the landlord's own
    name goes - must not fall back to the narrow default. It's "medium"
    rather than "long": the opening sentence packs three blanks (Lessor,
    Lessee, address) together, and three 5.5in "long" blanks in one short
    sentence is what originally made it look broken under justified text."""
    opening = real_output[real_output.index("<body>") :][:400]
    first_blank = opening.index('<span class="blank')
    assert opening[first_blank:].startswith('<span class="blank medium"></span>')


def test_preamble_paragraph_is_left_aligned_not_justified(real_output):
    """Three blanks packed into one short sentence stretch justified text
    into odd gaps around them; left-aligned, uneven line lengths read as
    normal instead."""
    assert '<p class="preamble">' in real_output


def test_a_month_name_blank_is_wider_than_a_two_digit_number_blank(real_output):
    """Regression guard for the actual bug: the old keyword-sniffing width
    heuristic looked far enough ahead to catch the *next* sentence's
    "Lessee"/"Lessor" and mis-sized §1 TERM's month/year blanks as "long"
    instead of something sized for what's actually written there."""
    term_area = real_output[real_output.index(">TERM<") :][:400]
    assert 'class="blank word"' in term_area  # a month name
    assert 'class="blank tiny"' in term_area  # a day or 2-digit year
    assert 'class="blank long"' not in term_area


def test_occupants_blanks_are_long_and_on_their_own_lines(real_output):
    occupants_area = real_output[real_output.index("OCCUPANTS") :][:400]
    assert occupants_area.count('<span class="blank long"></span>') >= 2
    assert "<br>" in occupants_area


# ---------------------------------------------------------------------------
# General structure
# ---------------------------------------------------------------------------

def test_lgd_branding_is_not_in_the_title(real_output):
    """This lease is shared across landlords; no single landlord's name
    belongs in a document title meant to be reused by all of them."""
    head = real_output[: real_output.index("<body>")]
    assert "LGD" not in head
    assert "RESIDENTIAL LEASE" in real_output


def test_page_number_counter_is_present(real_output):
    assert "counter(page)" in real_output
    assert "counter(pages)" in real_output


def test_printing_paginates_the_same_on_a_phone_as_on_a_desktop(real_output):
    """This printed 6 pages from a desktop but 9 from a phone. Two device
    differences cause that, and both have to stay pinned:

    1. Phones inflate the font of long text blocks (text autosizing) and
       carry that inflation onto paper.
    2. A phone lays the screen out ~390px wide, so a browser printing from
       the screen layout instead of re-flowing to paper wraps far more
       lines per paragraph.
    """
    assert "text-size-adjust: 100%" in real_output

    print_block = real_output.split("@media print {")[1].split("@media screen")[0]
    assert "max-width: none" in print_block
    assert "width: auto" in print_block


def test_page_auto_triggers_the_browser_print_dialog(real_output):
    """Opening this page (from the dashboard's "Print blank lease" button)
    is the whole point of it, so it must not sit there waiting for the
    landlord to find Ctrl+P themselves."""
    assert "window.print()" in real_output
    assert 'addEventListener("load"' in real_output


def test_page_size_is_letter(real_output):
    assert "size: letter;" in real_output


def test_signature_block_does_not_force_its_own_page(real_output):
    """Regression guard: the signature block used to be tall enough
    (~2.8in of margins alone) that it never fit on whatever page it
    landed on and got pushed onto a page entirely by itself. Confirmed by
    actually rendering to PDF with headless Chrome/Edge and checking the
    last page's content during development - this just locks in the CSS
    properties responsible so a future edit can't silently regress it."""
    assert "page-break-before: avoid;" in real_output
    signature_css = real_output[
        real_output.index(".signature-block {") : real_output.index(".sig-line {")
    ]
    assert "margin-top: 0.3in;" in signature_css


def test_all_twenty_sections_present_in_order(real_output):
    import re

    numbers = [int(n) for n in re.findall(r'class="section">(\d+)\.', real_output)]
    assert numbers == list(range(1, 21))


def test_footer_note_is_hidden_when_printed(real_output):
    assert ".footer-note { display: none; }" in real_output


# ---------------------------------------------------------------------------
# PARKING section: two real, mutually exclusive radio buttons, not blanks
# ---------------------------------------------------------------------------

def test_parking_is_the_last_numbered_section(real_output):
    import re

    numbers = [int(n) for n in re.findall(r'class="section">(\d+)\.', real_output)]
    assert numbers[-1] == 20
    assert "20. <strong>PARKING</strong>" in real_output


def test_parking_radios_are_real_inputs_not_blanks(real_output):
    assert '<input type="radio" name="parking" id="parking-not-available">' in real_output
    assert '<input type="radio" name="parking" id="parking-limited">' in real_output
    assert "Parking not available at this address." in real_output
    assert "Parking spaces are limited to the number of tenants" in real_output


def test_parking_options_are_wrapped_for_js_to_strike(real_output):
    assert '<label class="checkbox-line" id="parking-label-not-available">' in real_output
    assert '<label class="checkbox-line" id="parking-label-limited">' in real_output


def test_parking_radios_toggle_strikethrough(gen):
    import html as html_module

    marked = gen.markup_blanks(
        f"20. **PARKING** ( ) {gen.PARKING_MARKER_A_TEXT}  ( ) {gen.PARKING_MARKER_B_TEXT}",
        iter([]),
    )
    assert (
        '<label class="checkbox-line" id="parking-label-not-available">'
        '<input type="radio" name="parking" id="parking-not-available">'
        f"{html_module.escape(gen.PARKING_MARKER_A_TEXT)}</label>"
    ) in marked
    assert (
        '<label class="checkbox-line" id="parking-label-limited">'
        '<input type="radio" name="parking" id="parking-limited">'
        f"{html_module.escape(gen.PARKING_MARKER_B_TEXT)}</label>"
    ) in marked


def test_a_parking_answer_can_be_preselected_from_the_url(real_output):
    """The manager dashboard asks "off-street parking available?" before
    opening this page and passes the answer as ?parking=yes|no, so the
    lease is already set correctly by the time the print dialog opens."""
    assert 'get("parking")' in real_output
    assert 'parking === "yes"' in real_output
    assert 'parking === "no"' in real_output
    # Yes means parking exists but is limited; no means none at all.
    yes_branch = real_output.split('parking === "yes"')[1].split("else")[0]
    assert "parking-limited" in yes_branch
    no_branch = real_output.split('parking === "no"')[1].split("}")[0]
    assert "parking-not-available" in no_branch


def test_output_is_well_formed_enough_to_have_one_head_and_body(real_output):
    assert real_output.count("<html") == 1
    assert real_output.count("<body>") == 1
    assert real_output.count("</body>") == 1
    assert real_output.count("</html>") == 1


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------

def test_missing_execution_sentence_raises(gen):
    with pytest.raises(SystemExit):
        gen.generate("# Residential Lease\n\nNo execution sentence at all.\n")


def test_generation_is_deterministic(gen):
    text = SOURCE_PATH.read_text(encoding="utf-8")
    assert gen.generate(text) == gen.generate(text)


def test_generated_file_on_disk_matches_a_fresh_run(gen, real_output):
    output_path = Path(__file__).resolve().parent.parent / "print" / "lease_print.html"
    assert output_path.read_text(encoding="utf-8") == real_output
