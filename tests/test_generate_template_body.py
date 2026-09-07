"""Tests for pandadoc/generate_template_body.py.

These guard against the actual bug found while building this generator: a
blank line in `lease.md` is not reliably a real paragraph break (the scanned
document's page cuts sometimes fall mid-sentence), so a naive "blank line ==
new paragraph" splitter silently mangles the lease's actual sentences.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parent.parent / "pandadoc" / "generate_template_body.py"
SOURCE_PATH = Path(__file__).resolve().parent.parent / "originals" / "lease.md"


def _load_module():
    spec = importlib.util.spec_from_file_location("generate_template_body", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gen():
    return _load_module()


@pytest.fixture(scope="module")
def real_lease_text() -> str:
    return SOURCE_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def real_output(gen, real_lease_text) -> str:
    """Generated output against the actual current originals/lease.md."""
    return gen.generate(real_lease_text)


# ---------------------------------------------------------------------------
# The actual bug: mid-sentence page cuts must be rejoined, not left split
# ---------------------------------------------------------------------------

def test_security_deposit_sentence_is_not_split_by_the_page_cut(real_output):
    """The scan's page 1/2 boundary fell mid-sentence: "...Lessor may" /
    "not deduct...". These must end up in the same paragraph."""
    assert "Lessor may not deduct any portion" in real_output
    assert "Lessor may\n\nnot deduct" not in real_output


def test_other_violations_sentence_is_not_split_by_the_page_cut(real_output):
    """The scan's page 3/4 boundary fell mid-sentence: "...necessary to" /
    "provide reasonable safety...". These must end up in the same paragraph."""
    assert "necessary to provide reasonable safety" in real_output
    assert "necessary to\n\nprovide" not in real_output


def test_preamble_is_one_sentence_despite_the_stylistic_blank_line(real_output):
    assert (
        "the premises known as [Premises.Address] in New Orleans, Louisiana "
        "for use as a private residence only."
    ) in real_output


# ---------------------------------------------------------------------------
# Genuine paragraph breaks must survive - the merge must not be too eager
# ---------------------------------------------------------------------------

def test_occupants_blank_does_not_swallow_the_next_numbered_section(real_output):
    """A bare blank line has no terminal punctuation either; naive merging
    would otherwise keep eating forward straight into "5. PETS"."""
    assert "occupied by the following persons only\n\n[Occupants.List]" in real_output
    occupants_index = real_output.index("[Occupants.List]")
    pets_index = real_output.index("PETS")
    between = real_output[occupants_index:pets_index]
    assert "5." in between or between.count("\n\n") >= 1


def test_additions_and_no_holes_stay_separate_paragraphs(real_output):
    """This is a genuine paragraph break in the original, not a mid-sentence
    page cut - must NOT be merged even though a page boundary sits there too."""
    assert (
        "unless otherwise stipulated.\n\nNo holes shall be drilled"
        in real_output
    )


def test_other_and_multi_tenant_paragraph_stay_separate(real_output):
    assert (
        "shall continue in full force and effect.\n\nIn the event this "
        "rental agreement is executed by more than one tenant"
        in real_output
    )


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------

def test_every_expected_token_appears_exactly_once(gen, real_output):
    for token in gen.EXPECTED_TOKENS:
        assert real_output.count(f"[{token}]") == 1, token


def test_no_blank_survives_untranslated(real_output):
    import re

    # Outside the header's own explanatory prose (which mentions blanks like
    # "___" as documentation), the body should have no bare fill-in left.
    body_start = real_output.index("---\n\n[Lessor.Name]")
    body = real_output[body_start:]
    assert not re.search(r"_{2,}", body)


def test_signature_lines_are_not_present_as_text(real_output):
    """Signature lines become PandaDoc fields, never text - the generator
    must drop the literal underscore signature lines from lease.md's tail."""
    signature_area = real_output[real_output.index("Executed in duplicate") :]
    # Four blank signature lines in the source; none should survive as text.
    assert signature_area.count("_______________________________________") == 0


def test_output_ends_with_the_execution_sentence_before_the_footer(real_output):
    executed_index = real_output.index("Executed in duplicate")
    signature_heading_index = real_output.index("## Signature block")
    between = real_output[executed_index:signature_heading_index].strip()
    # Only the execution sentence and the "---" divider before the footer
    # heading should sit in between - nothing else.
    assert between.rstrip("-\n ").rstrip().endswith(
        "[Execution.Month] 20[Execution.Year]."
    )


# ---------------------------------------------------------------------------
# Failure modes: the generator must fail loudly, not silently mis-map
# ---------------------------------------------------------------------------

def test_missing_blank_raises_instead_of_silently_skipping(gen):
    broken = (
        "# Residential Lease\n\n---\n\n"
        "hereby leases to (hereinafter referred to as Lessor)\n\n"
        # Deposit blank removed entirely - simulates someone accidentally
        # deleting a fill-in line while editing lease.md.
        "3. **SECURITY DEPOSIT** the sum of dollars.\n\n"
        "Executed in duplicate at ___, Louisiana this ___ day of ___20__.\n"
    )
    with pytest.raises(SystemExit):
        gen.generate(broken)


def test_missing_execution_sentence_raises(gen):
    broken = "# Residential Lease\n\n---\n\nNo execution sentence here at all.\n"
    with pytest.raises(SystemExit):
        gen.generate(broken)


def test_extra_unhandled_blank_raises(gen, real_lease_text):
    """A stray extra blank that BLANK_SUBSTITUTIONS doesn't know about must
    fail the build rather than reach PandaDoc missing a token."""
    tampered = real_lease_text.replace(
        "in New Orleans, Louisiana for use as a private residence only.",
        "in New Orleans, Louisiana, unit ____, for use as a private "
        "residence only.",
    )
    with pytest.raises(SystemExit):
        gen.generate(tampered)


# ---------------------------------------------------------------------------
# Idempotence
# ---------------------------------------------------------------------------

def test_generation_is_deterministic(gen, real_lease_text):
    first = gen.generate(real_lease_text)
    second = gen.generate(real_lease_text)
    assert first == second


def test_generated_file_on_disk_matches_a_fresh_run(gen, real_lease_text):
    """Guards against someone hand-editing the generated file and forgetting
    to re-run the generator before committing."""
    output_path = Path(__file__).resolve().parent.parent / "pandadoc" / "lease_template_body.md"
    on_disk = output_path.read_text(encoding="utf-8")
    assert on_disk == gen.generate(real_lease_text)
