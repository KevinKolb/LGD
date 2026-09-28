"""Tests for documents/print/generate_print_deposit.py - the printable
security deposit agreement, built from documents/security_deposit.md with
the lease generator's header, font and apartment picker."""
from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "documents" / "print" / "generate_print_deposit.py"
SOURCE_PATH = ROOT / "documents" / "security_deposit.md"
TRANSCRIPT_PATH = ROOT / "documents" / "originals" / "security_deposit_transcript_verbatim.md"


@pytest.fixture(scope="module")
def gen():
    spec = importlib.util.spec_from_file_location("generate_print_deposit", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def real_output(gen) -> str:
    return gen.generate(SOURCE_PATH.read_text(encoding="utf-8"))


def test_the_header_matches_the_lease_format(real_output):
    body = real_output[real_output.index("<body>"):]
    assert '<h1 class="company">Lower Garden District Properties, Inc.</h1>' in body
    assert '<p class="subtitle">SECURITY DEPOSIT AGREEMENT</p>' in body
    assert "<title>Security Deposit Agreement</title>" in real_output


def test_the_original_letterhead_is_not_on_the_live_form(real_output):
    """The scanned form was Steve A. Hartnett's; the live one is LGD's."""
    assert "HARTNETT" not in real_output.upper()
    assert "1556 Camp" not in real_output


def test_the_premises_blank_is_filled_by_the_picker(real_output):
    assert real_output.count('id="premises"') == 1
    assert re.search(r'As Security Deposit for <span class="blank \w+" id="premises"></span>', real_output)
    assert 'id="picker"' in real_output
    assert "Which apartment is this security deposit for?" in real_output
    assert '<script type="application/json" id="lease-properties">' in real_output


def test_all_fourteen_conditions_in_order_across_the_page_break(real_output):
    lists = re.findall(r'<ol class="conditions" start="(\d+)">(.*?)</ol>', real_output, re.S)
    assert [start for start, _ in lists] == ["1", "13"]
    assert sum(body.count("<li>") for _, body in lists) == 14


def test_both_signature_groups_are_bound_to_what_they_sign(real_output):
    blocks = re.findall(r'<div class="execution-block">(.*?)</div>\n</div>', real_output, re.S)
    assert len(blocks) == 2
    assert "may not be applied as rent" in blocks[0]
    assert "refunded to applicant" in blocks[1]
    assert real_output.count('<div class="sig-line">Lessee</div>') == 6


def test_the_font_is_embedded(real_output):
    assert 'font-family: "Gelasio"' in real_output
    assert "data:font/woff2;base64," in real_output


def test_unversioned_conditions_still_match_the_transcript(gen):
    """The live master started as the transcript minus its letterhead and
    title. Conditions 6 and 9 became address-dependent on 2026-09-28 (see
    documents/security_deposit_history.md); every other one must still be
    there word for word until a change is deliberately made and logged."""
    transcript = TRANSCRIPT_PATH.read_text(encoding="utf-8")
    source = SOURCE_PATH.read_text(encoding="utf-8")
    for match in re.finditer(r"^(\d+)\. (.+)$", transcript, re.M):
        if int(match.group(1)) in gen.ITEM_OPTIONS:
            continue
        assert match.group(0) in source


def test_walls_and_yard_conditions_have_the_leases_versions(gen, real_output):
    """Conditions 6 and 9 carry one version per lease option, tagged like
    the lease's, so the shared picker shows the deposit that matches the
    lease for the same apartment."""
    assert gen.ITEM_OPTIONS == {6: "walls", 9: "yard"}
    items = re.findall(r"<li>(.*?)</li>", real_output, re.S)
    for number, group in gen.ITEM_OPTIONS.items():
        for value in gen.lease.OPTION_GROUPS[group]:
            assert f'data-option="{group}={value}"' in items[number - 1]
    # Plaster (B) repeats everything standard (A) forbids, then adds its own.
    assert items[5].count("No stickers, scratches, or holes") == 2
    assert "eight (8) pounds" in items[5]
    assert "Section 17 of the lease" in items[8]


def test_a_versioned_condition_that_moves_fails_the_build(gen):
    broken = SOURCE_PATH.read_text(encoding="utf-8").replace("6. (A) No stickers", "6. No stickers")
    with pytest.raises(SystemExit, match="Condition 6"):
        gen.generate(broken)


def test_a_skipped_condition_number_fails_the_build(gen):
    broken = SOURCE_PATH.read_text(encoding="utf-8").replace("5. No damage", "6. No damage")
    with pytest.raises(SystemExit):
        gen.generate(broken)


def test_a_missing_premises_blank_fails_the_build(gen):
    broken = SOURCE_PATH.read_text(encoding="utf-8").replace("As Security Deposit for", "Deposit for")
    with pytest.raises(SystemExit, match="premises"):
        gen.generate(broken)


def test_generated_file_on_disk_matches_a_fresh_run(gen, real_output):
    assert gen.OUTPUT.read_text(encoding="utf-8") == real_output


def test_the_page_script_parses(real_output, tmp_path):
    """The picker script is shared with the lease; its parking handlers must
    not throw on a page with no parking section."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    for index, script in enumerate(re.findall(r"<script>(.*?)</script>", real_output, re.S)):
        path = tmp_path / f"script{index}.js"
        path.write_text(script, encoding="utf-8")
        result = subprocess.run([node, "--check", str(path)], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
    assert "if (notAvailable && limited)" in real_output
