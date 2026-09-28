"""Tests for documents/print/generate_print_addendum.py - the Plaster Walls
Addendum, whose rules are read out of lease §20 WALLS version (B)."""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "documents" / "print" / "generate_print_addendum.py"
LEASE_PATH = ROOT / "documents" / "lease.md"


@pytest.fixture(scope="module")
def gen():
    spec = importlib.util.spec_from_file_location("generate_print_addendum", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def real_output(gen) -> str:
    return gen.generate(LEASE_PATH.read_text(encoding="utf-8"))


def test_the_header_matches_the_lease(gen, real_output):
    assert f'<h1 class="company">{gen.lease.COMPANY_NAME}</h1>' in real_output
    assert '<p class="subtitle">PLASTER WALLS ADDENDUM</p>' in real_output


def test_it_is_incorporated_into_the_existing_lease_for_1523(real_output):
    assert "made part of and incorporated into the Lease Agreement dated" in real_output
    assert "<strong><u>1523 St. Andrew St., New Orleans, LA 70130</u></strong>" in real_output
    assert "this Addendum controls" in real_output


def test_the_rules_are_the_leases_plaster_version_word_for_word(gen, real_output):
    """Read from lease.md, never copied - so the two cannot drift apart."""
    blocks = gen.walls_version_blocks(LEASE_PATH.read_text(encoding="utf-8"))
    assert blocks[0].startswith("The walls and ceilings of the leased premises are historical")
    assert any("eight (8) pounds" in b for b in blocks)
    assert not any(b.startswith("(A) ") or "(B) " in b for b in blocks)
    for block in blocks:
        assert gen.lease.convert_bold(__import__("html").escape(block)) in real_output
    # Nothing from the standard version (A) that is not also in (B).
    assert "for hanging pictures" not in real_output


def test_it_has_a_signature_and_date_for_lessor_and_three_lessees(real_output):
    assert real_output.count('<div class="sig-row">') == 4
    assert real_output.count('<div class="sig-line date">Date</div>') == 4
    labels = re.findall(r'<div class="sig-row"><div class="sig-line">([^<]+)</div>', real_output)
    assert labels == ["Lessor/Agent", "Lessee", "Lessee", "Lessee"]


def test_signatures_are_bound_to_the_acknowledgement(real_output):
    block = real_output[real_output.index('<div class="execution-block">'):]
    assert "By signing below" in block[:block.index('<div class="signature-block">')]


def test_the_font_is_embedded_and_the_page_prints_itself(real_output):
    assert "data:font/woff2;base64," in real_output
    assert "window.print()" in real_output
    assert 'window.location.hash === "#view"' in real_output


def test_generated_file_on_disk_matches_a_fresh_run(gen, real_output):
    assert gen.OUTPUT.read_text(encoding="utf-8") == real_output
