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

def test_the_lessor_name_blank_is_long(real_output):
    """The very first blank in the document - where the landlord's own
    name goes - was sized "short" because "Lessor" sits far enough after
    it that the old, narrower lookahead window never saw it."""
    opening = real_output[real_output.index("<body>") :][:400]
    first_blank = opening.index('<span class="blank')
    assert opening[first_blank:].startswith('<span class="blank long"></span>')


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
        gen.generate("# LGD Residential Lease\n\nNo execution sentence at all.\n")


def test_generation_is_deterministic(gen):
    text = SOURCE_PATH.read_text(encoding="utf-8")
    assert gen.generate(text) == gen.generate(text)


def test_generated_file_on_disk_matches_a_fresh_run(gen, real_output):
    output_path = Path(__file__).resolve().parent.parent / "print" / "lease_print.html"
    assert output_path.read_text(encoding="utf-8") == real_output
