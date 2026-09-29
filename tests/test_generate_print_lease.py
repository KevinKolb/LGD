"""Tests for documents/print/generate_print_lease.py.

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
import re
import sys
from pathlib import Path

import pytest

MODULE_PATH = (Path(__file__).resolve().parent.parent
                / "documents" / "print" / "generate_print_lease.py")
SOURCE_PATH = Path(__file__).resolve().parent.parent / "documents" / "lease.md"


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
    signature_area = signature_area[: signature_area.index("</div>\n</div>")]
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
    """The very first blank in the document - where the manager's own
    name goes - must not fall back to the narrow default. It's "medium"
    rather than "long": the opening sentence packs three blanks (Lessor,
    Lessee, address) together, and three 5.5in "long" blanks in one short
    sentence is what originally made it look broken under justified text."""
    opening = real_output[real_output.index("<body>") :][:400]
    # The first blank is the Lessor's, filled with the company name.
    first_blank = re.search(r'<span (?:data-fill="\w+" )?class="blank[^"]*"', opening).group(0)
    assert first_blank == '<span data-fill="lessor" class="blank medium"'
    assert "<body>" in real_output and '<main class="sheet">' in opening


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
    assert len(re.findall(r'<span (?:data-fill="occupants" )?class="blank long"></span>', occupants_area)) >= 2
    assert "<br>" in occupants_area


# ---------------------------------------------------------------------------
# General structure
# ---------------------------------------------------------------------------

def test_the_manager_name_heads_the_lease(real_output):
    """This was a blank line for a while, so one form could be shared across
    every manager in accounts.json. Printing a name here means the form is
    LGD's; another manager would need their own copy."""
    body = real_output[real_output.index("<body>") :]
    assert "Lower Garden District Properties, Inc." in body
    assert "LLC" not in real_output
    assert "RESIDENTIAL LEASE" in body
    # The name comes first, above the document type.
    assert body.index("Lower Garden District") < body.index("RESIDENTIAL LEASE")


def test_the_browser_tab_title_carries_no_manager_name(real_output):
    """Only the printed page is LGD's - the <title> is what a browser shows
    and what a saved PDF gets named by default, and stays generic. Checked
    on the tag alone, not the whole <head>: the manager name legitimately
    appears there too, inside the @page margin boxes."""
    title = real_output[real_output.index("<title>") : real_output.index("</title>")]
    assert title == "<title>Residential Lease"
    assert "LGD" not in title


def test_page_number_counter_is_at_the_top_and_bottom_of_every_page(real_output):
    """"Page N of M" in both @page margin boxes. Chrome and Edge do render
    these - verified by printing the same document with and without the
    boxes and diffing the PDFs, since the text itself is not extractable
    from a subset-font PDF."""
    page_rule = real_output.split("@page {")[1].split("html, body")[0]
    assert "@top-center" in page_rule
    assert "@bottom-center" in page_rule
    assert page_rule.count("counter(page)") == 2
    assert page_rule.count("counter(pages)") == 2
    # The manager name leads both, so a loose page is identifiable.
    assert page_rule.count("Lower Garden District Properties, Inc. — Page ") == 2


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
    # An absolute width, not "auto": auto still resolves against whatever
    # narrow box the browser laid out at, which is exactly the bug. 6.8in is
    # Letter's 8.5in less the 0.85in @page margin on each side. Measured:
    # a 390px column reproduces the 9-page output, 6.8in restores 6.
    declarations = re.sub(r"/\*.*?\*/", "", print_block, flags=re.DOTALL)
    assert "width: 6.8in;" in declarations
    assert "max-width: 6.8in;" in declarations
    assert "width: auto;" not in declarations


def test_page_auto_triggers_the_browser_print_dialog(real_output):
    """Opening this page (from the dashboard's "Print blank lease" button)
    is the whole point of it, so it must not sit there waiting for the
    manager to find Ctrl+P themselves."""
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


def test_all_twenty_one_sections_present_in_order(real_output):
    import re

    numbers = [int(n) for n in re.findall(r'class="section">(\d+)\.', real_output)]
    assert numbers == list(range(1, 22))


def test_footer_note_is_hidden_when_printed(real_output):
    assert ".footer-note { display: none; }" in real_output


# ---------------------------------------------------------------------------
# PARKING section: two real, mutually exclusive radio buttons, not blanks
# ---------------------------------------------------------------------------

def test_parking_is_the_last_numbered_section(real_output):
    import re

    numbers = [int(n) for n in re.findall(r'class="section">(\d+)\.', real_output)]
    assert numbers[-1] == 21
    assert "21. <strong>PARKING</strong>" in real_output


def test_parking_radios_are_real_inputs_not_blanks(real_output):
    assert '<input type="radio" name="parking" id="parking-not-available">' in real_output
    assert '<input type="radio" name="parking" id="parking-limited">' in real_output
    assert "Parking not available at this address." in real_output
    assert "Parking spaces are limited to the number of tenants" in real_output


def test_parking_options_are_wrapped_for_js_to_strike(real_output):
    assert ('<label class="checkbox-line" id="parking-label-not-available"'
            ' data-option="parking=not-available">') in real_output
    assert ('<label class="checkbox-line" id="parking-label-limited"'
            ' data-option="parking=limited">') in real_output


def test_parking_radios_toggle_strikethrough(gen):
    import html as html_module

    marked = gen.markup_blanks(
        f"20. **PARKING** ( ) {gen.PARKING_MARKER_A_TEXT}  ( ) {gen.PARKING_MARKER_B_TEXT}",
        iter([]),
    )
    assert (
        '<label class="checkbox-line" id="parking-label-not-available"'
        ' data-option="parking=not-available">'
        '<input type="radio" name="parking" id="parking-not-available">'
        f"{html_module.escape(gen.PARKING_MARKER_A_TEXT)}</label>"
    ) in marked
    assert (
        '<label class="checkbox-line" id="parking-label-limited"'
        ' data-option="parking=limited">'
        '<input type="radio" name="parking" id="parking-limited">'
        f"{html_module.escape(gen.PARKING_MARKER_B_TEXT)}</label>"
    ) in marked



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
    output_path = (Path(__file__).resolve().parent.parent
                   / "documents" / "print" / "lease_print.html")
    assert output_path.read_text(encoding="utf-8") == real_output

def test_the_font_is_embedded_so_pagination_cannot_depend_on_the_device(gen, real_output):
    """The lease printed 6 pages from a desktop but put the signatures on a
    near-empty page of their own from a phone. Root cause: the document asked
    for Georgia, and a device that does not have Georgia silently substitutes
    something with different advance widths - different line breaks, different
    page ends. Measured with headless Chrome, dropping Georgia from the stack
    moved the per-page character counts from
    [2838, 2422, 3060, 2923, 3101, 2091] to
    [2777, 3154, 3682, 3140, 3253, 429] - that last page is the bug.

    Embedding the font removes the substitution entirely: the same two
    renders now match to the character. So the font has to stay inline, and
    it has to stay first in the stack.
    """
    assert "data:font/woff2;base64," in real_output
    # First in the stack everywhere it is declared, or the fallback wins.
    for stack in re.findall(r"font-family:([^;]+);", real_output):
        assert stack.strip().startswith('"Gelasio"'), stack

    # A weight *range*: one variable file covering regular through bold. A
    # static face would leave each engine to synthesize its own bold, and
    # synthesized bold differs per engine - the same class of variance.
    assert "font-weight: 400 700;" in real_output

    # block, not swap: printing must not start in a fallback face.
    assert "font-display: block;" in real_output


def test_embedded_font_bytes_round_trip(gen, real_output):
    """The data URI must decode to the font actually committed, so a
    truncated or re-encoded blob is caught here rather than on paper."""
    import base64

    encoded = re.search(r"data:font/woff2;base64,([A-Za-z0-9+/=]+)", real_output).group(1)
    assert base64.b64decode(encoded) == gen.FONT_FILE.read_bytes()


def test_printing_waits_for_the_font(real_output):
    """window.print() on "load" can fire while the document is still laid
    out in a fallback face, which paginates on the wrong widths - the very
    thing embedding the font is meant to prevent."""
    assert "document.fonts" in real_output
    assert "fontsReady" in real_output


def test_signatures_are_bound_to_the_sentence_they_execute(real_output):
    """A page break between "Executed in duplicate at ___" and the signature
    lines leaves a bare signature page. Verified with headless Chrome across
    Letter and A4 at six margin settings: 12 of 12 keep them together.

    This is deliberately a relative constraint rather than a fixed page
    position - that is what makes it survive a different paper size, a
    different margin, or a different printer.
    """
    block = real_output[real_output.index('<div class="execution-block">'):]
    block = block[:block.index("</div>", block.index("signature-block"))]
    assert "Executed in duplicate at" in block
    assert "Lessor/Agent" in block

    css = real_output[real_output.index(".execution-block {"):real_output.index(".signature-block {")]
    assert "page-break-inside: avoid;" in css
    assert "break-inside: avoid;" in css


# ---------------------------------------------------------------------------
# Apartment picker: documents/properties.json fills in the premises and
# crosses out the lease options that do not apply
# ---------------------------------------------------------------------------

def test_the_apartment_table_is_inlined_not_fetched(gen, real_output):
    """Inlined like the font, so the page stays one file that works offline."""
    import json

    start = real_output.index('<script type="application/json" id="lease-properties">')
    body = real_output[real_output.index(">", start) + 1:real_output.index("</script>", start)]
    assert json.loads(body) == gen.load_properties()
    assert "fetch(" not in real_output


def test_the_premises_blank_is_the_one_the_picker_fills(real_output):
    assert real_output.count('id="premises"') == 1
    assert 'the premises known as <span class="blank medium" id="premises"></span>' in real_output


LABEL = '<span class="version-label">'


def test_the_patio_yard_section_holds_both_yard_versions(real_output):
    """The heading belongs to the whole group and always shows; A and B are
    each tagged on their own, so the one that does not apply is hidden."""
    assert re.search(r'<p data-option="yard=any" class="section">\d+\. <strong>PATIO/YARD</strong> '
                     r'<span data-option="yard=A">' + re.escape(LABEL) + r'\(A\) </span>The patio/yard',
                     real_output)
    assert re.search(r'<p data-option="yard=B">' + re.escape(LABEL) + r'\(B\) </span>The patio/yard, '
                     r'alley, front yard', real_output)


def test_the_popup_summarises_every_option_value(gen, real_output):
    """The popup lists parking, walls and yard for the chosen address; a
    value added to OPTION_GROUPS without a summary line would show blank."""
    summary = real_output[real_output.index("var SUMMARY = {"):real_output.index("function showUnits")]
    for group, values in gen.OPTION_GROUPS.items():
        line = summary[summary.index(f"{group}: {{"):]
        line = line[:line.index("}")]
        for value in values:
            assert re.search(rf'"?{re.escape(value)}"?: "', line), (group, value)


def test_parking_radios_are_not_mistaken_for_versions(gen):
    marked = gen.mark_versions("<p>( ) Parking not available.</p>", "parking=any")
    assert "<span" not in marked


def test_every_address_dependent_section_is_on_every_lease(real_output):
    """Section numbers must match across leases, so these three sections'
    headings are tagged "any" - never hidden, whichever version applies."""
    for title, group in (("PATIO/YARD", "yard"), ("WALLS", "walls"), ("PARKING", "parking")):
        assert re.search(rf'<p data-option="{group}=any" class="section">\d+\. <strong>{re.escape(title)}</strong>',
                         real_output)
    script = real_output[real_output.index("function applyProperty"):]
    assert 'option.value === "any") { return; }' in script


def test_an_option_with_no_tagged_wording_fails_the_build(gen, monkeypatch):
    monkeypatch.setitem(gen.OPTION_GROUPS, "yard", {"A", "B", "C"})
    with pytest.raises(SystemExit, match="yard=C"):
        gen.generate(SOURCE_PATH.read_text(encoding="utf-8"))


def test_a_renamed_option_section_fails_the_build(gen, monkeypatch):
    monkeypatch.setitem(gen.SECTION_OPTIONS, "NO SUCH SECTION", "yard=Z")
    with pytest.raises(SystemExit, match="NO SUCH SECTION"):
        gen.generate(SOURCE_PATH.read_text(encoding="utf-8"))


def test_the_picker_never_reaches_paper(real_output):
    print_css = real_output[real_output.index("@media print {"):]
    assert ".picker { display: none !important; }" in print_css


def test_versions_that_do_not_apply_are_hidden_not_crossed_out(real_output):
    """The user's call on 2026-09-28: a lease shows only the wording that
    applies to its address - hidden, so a blank lease can still show them
    all - and never crossed out."""
    script = real_output[real_output.index("function applyProperty"):]
    script = script[:script.index("function finish")]
    assert "element.hidden = !applies" in script
    assert "struck" not in script
    assert ".remove()" not in script


def test_printing_waits_for_the_apartment_to_be_picked(real_output):
    """window.print() is called only from finish(), which runs once the
    manager has picked an apartment or chosen to leave it blank."""
    script = real_output[real_output.index("function finish"):]
    assert "window.print()" in script[:script.index("properties.forEach")]
    # The only other call is the floating Print button's, and that button
    # starts hidden and is shown only by finish() - so it too waits.
    assert real_output.count("window.print()") == 2
    assert '<button type="button" id="print-button" hidden>Print</button>' in real_output
    finish = script[:script.index("properties.forEach")]
    assert 'getElementById("print-button").hidden = false' in finish
    assert real_output.count('getElementById("print-button").hidden = false') == 1


def test_back_and_print_float_on_screen_and_never_print(real_output):
    """Everything opens in the same tab, so a document carries its own way
    back beside its Print button; neither may appear on paper."""
    css = real_output[real_output.index(".float-buttons {"):]
    assert "position: fixed;" in css[:css.index("}")]
    printed = real_output[real_output.index("@media print {"):]
    assert ".float-buttons { display: none !important; }" in printed[:printed.index("\n  }")]
    buttons = real_output[real_output.index('<div class="float-buttons">'):]
    buttons = buttons[:buttons.index("</div>")]
    assert '<a href="../../manager/" id="back-button">Back</a>' in buttons
    assert 'id="print-button"' in buttons
    assert "window.history.back()" in real_output

@pytest.mark.parametrize("prop, message", [
    ({"id": "x", "address": "1 A St.", "units": [], "lease_options": {"parking": "maybe"}},
     "parking must be one of"),
    ({"id": "x", "address": "1 A St.", "units": [], "lease_options": {"garage": "yes"}},
     "unknown lease option"),
    ({"id": "x", "address": "1 A St.", "units": ["1", "1"], "lease_options": {}},
     "distinct"),
    ({"id": "x", "units": [], "lease_options": {}},
     "missing 'address'"),
    ({"id": "x", "address": "1 A St.", "units": [], "lease_options": {"parking": "limited", "walls": "A"}},
     "yard must be one of"),
    ({"id": "x", "address": "1 A St.", "units": [],
      "lease_options": {"parking": "none", "walls": "A", "yard": "A"}},
     "parking must be one of"),
])
def test_a_bad_apartment_entry_fails_the_build(gen, prop, message):
    with pytest.raises(SystemExit, match=message):
        gen.validate_properties({"properties": [prop]})


def test_duplicate_apartment_ids_fail_the_build(gen):
    prop = {"id": "x", "address": "1 A St.", "units": [],
            "lease_options": {"parking": "limited", "walls": "A", "yard": "A"}}
    with pytest.raises(SystemExit, match="used twice"):
        gen.validate_properties({"properties": [prop, dict(prop)]})


def test_the_real_apartment_table_is_valid(gen):
    data = gen.load_properties()
    assert data["manager_id"] == "lgd"
    assert data["properties"]


def test_a_closing_script_tag_in_the_data_cannot_escape_it(gen):
    assert "</script>" not in gen.properties_json({"x": "</script>"})

def test_every_paragraph_of_the_plaster_version_is_tagged(real_output):
    """Walls version B (plaster) runs over several paragraphs and bullets;
    hiding it has to hide all of them, while version A sits in the heading
    paragraph."""
    start = real_output.index("<strong>WALLS</strong>")
    end = real_output.index("<strong>PARKING</strong>")
    section = real_output[real_output.rindex("<p", 0, start):end]
    paragraphs = re.findall(r"<p[^>]*>", section)
    assert paragraphs[0].startswith('<p data-option="walls=any"')
    assert '<span data-option="walls=A">' in section
    assert len(paragraphs) > 5
    assert all('data-option="walls=B"' in p for p in paragraphs[1:-1])


def test_the_execution_sentence_is_never_struck_with_the_last_section(real_output):
    block = real_output[real_output.index('<div class="execution-block">'):]
    assert "data-option" not in block[:block.index("</p>")]


def test_continuation_paragraphs_of_untagged_sections_stay_untagged(real_output):
    """Section 14 runs onto a second page - that paragraph is not an option."""
    holes = real_output.index("No holes shall be drilled")
    assert "data-option" not in real_output[real_output.rindex("<p", 0, holes):holes]

def test_the_page_script_parses(real_output, tmp_path):
    """HTML_FOOTER is an ordinary Python string, so a \\" written in its
    JavaScript loses the backslash and breaks the whole script - which is
    exactly what happened while the apartment picker was being built: the
    popup rendered with empty dropdowns and dead buttons. Checked with a
    real JavaScript parser when one is installed."""
    import shutil
    import subprocess

    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    scripts = re.findall(r"<script>(.*?)</script>", real_output, re.S)
    assert scripts
    for index, script in enumerate(scripts):
        path = tmp_path / f"script{index}.js"
        path.write_text(script, encoding="utf-8")
        result = subprocess.run([node, "--check", str(path)], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr

def test_bullet_items_are_their_own_indented_paragraphs(real_output):
    """The walls section's hardware lists are "• " paragraphs in lease.md;
    each renders as its own list item, still tagged with its section."""
    bullets = re.findall(r'<p data-option="walls=B" class="bullet">• ', real_output)
    assert len(bullets) == 6
    assert "p.bullet {" in real_output

def test_on_screen_the_document_is_a_sheet_of_letter_paper(real_output):
    """Viewed - on a phone especially - a document looks like the paper it
    prints on: an 8.5in sheet with the print margins, zoomed to fit the
    screen, so every line breaks where it will on paper. Measured in
    headless Chrome as iPhone SE, 13 and Pixel 7: no page is wider than the
    screen, and every printed page is unchanged."""
    screen = real_output[real_output.index("  @media screen {\n    html, body"):]
    sheet = screen[screen.index(".sheet {"):]
    sheet = sheet[:sheet.index("}")]
    assert "width: 8.5in;" in sheet and "padding: 0.85in;" in sheet
    assert "size: letter;" in real_output and "margin: 0.85in;" in real_output
    assert "function fitSheets()" in real_output
    assert '<main class="sheet">' in real_output
    # In print the sheet is no box at all, and never zoomed.
    printed = real_output[real_output.index("  @media print {\n    /* The wrappers"):]
    assert ".sheet, .sheet-stack, section.document { display: contents; zoom: 1 !important; }" in printed

def test_the_popup_scrolls_on_a_short_screen(real_output):
    """Centred with align-items, a popup taller than a phone screen was cut
    off at the top with no way to scroll up to it."""
    picker = real_output[real_output.index("  .picker {"):]
    assert "overflow-y: auto;" in picker[:picker.index("}")]
    assert "align-items: center;" not in picker[:picker.index("}")]
    box = real_output[real_output.index("  .picker-box {"):]
    assert "margin: auto;" in box[:box.index("}")]


def test_documents_float_back_and_print_but_no_home(real_output):
    """Every other page has Home; a document does not (the user,
    2026-09-29) - Back returns to the page that opened it."""
    buttons = real_output[real_output.index('<div class="float-buttons">'):]
    buttons = buttons[:buttons.index("</div>")]
    assert buttons.index('id="back-button"') < buttons.index('id="print-button"')
    assert "Home" not in buttons
    assert 'id="picker-home"' not in real_output
    assert 'id="home-button"' not in real_output


def test_numbers_use_lining_figures(real_output):
    """Every digit the height of a capital: Gelasio defaults to old-style
    figures, where "3,000" reads as a big 3 and small zeros (the user,
    2026-09-29). Also in the page-number lines."""
    body = real_output[real_output.index("  body {\n    font-family"):]
    body = body[:body.index("}")]
    assert "font-variant-numeric: lining-nums;" in body
    assert 'font-feature-settings: "lnum" 1;' in body
    page = real_output[real_output.index("@page {"):real_output.index("html, body {")]
    assert page.count("font-variant-numeric: lining-nums;") == 2


def test_every_lease_blank_is_tagged_with_what_fills_it(gen, real_output):
    """In order: Lessor, Lessee, premises, the term's start and end, rent,
    net rent, deposit, occupants, and where and when it is signed."""
    tags = re.findall(r'<span (?:data-fill="([\w-]+)" )?class="blank', real_output)
    assert tuple(tag or None for tag in tags) == gen.LEASE_FILLS


def test_a_blank_added_to_the_lease_fails_the_build(gen):
    with pytest.raises(SystemExit, match="fill list"):
        gen.tag_blanks('<span class="blank"></span>', ("a", "b"), "lease.md")


def test_dates_start_blank_with_a_today_switch(real_output):
    """The user, 2026-09-29: blank by default; Today fills in today's date,
    which stays editable."""
    for key in ("start", "signed"):
        assert re.search(rf'<input type="date" id="q-{key}" data-q="{key}"( data-default="[\w-]+")?>', real_output)
        assert f'<input type="checkbox" class="switch" id="q-{key}-today" data-today-for="q-{key}">' in real_output
    assert "if (toggle.checked) { date.value = isoToday(); }" in real_output


def test_values_worked_out_from_the_answers(real_output):
    """Net rent is rent less the $50 deduction; the lease ends the day
    before the same date a term later; the deposit is also written out."""
    assert 'values["net-rent"] = money(String(rent - 50));' in real_output
    assert "new Date(start.getFullYear(), start.getMonth() + months, start.getDate() - 1)" in real_output
    assert '"deposit-words": inWords(answer("deposit"))' in real_output
    assert '"signed-city": property.city || "New Orleans"' in real_output


def test_the_lease_starts_on_the_first_of_next_month_by_default(real_output):
    """The user, 2026-09-29: the start date opens at the first of next
    month; Today and typing still work, and Today off goes back to it. The
    signing date still opens blank."""
    assert '<input type="date" id="q-start" data-q="start" data-default="next-month">' in real_output
    assert '<input type="date" id="q-signed" data-q="signed">' in real_output
    assert "new Date(now.getFullYear(), now.getMonth() + 1, 1)" in real_output
    assert "date.value = dateDefault(date);" in real_output
