"""Tests for documents/print/generate_print_application.py - the printable
rental application, built from documents/application.md with the lease
generator's header, font and apartment picker."""
from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "documents" / "print" / "generate_print_application.py"
SOURCE_PATH = ROOT / "documents" / "application.md"


@pytest.fixture(scope="module")
def gen():
    spec = importlib.util.spec_from_file_location("generate_print_application", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def real_output(gen) -> str:
    return gen.generate(SOURCE_PATH.read_text(encoding="utf-8"))


def test_the_header_matches_the_lease(gen, real_output):
    assert f'<h1 class="company">{gen.lease.COMPANY_NAME}</h1>' in real_output
    assert '<p class="subtitle">APPLICATION FOR APARTMENT</p>' in real_output
    assert "LLC" not in real_output


def test_the_original_letterhead_is_not_on_the_live_form(real_output):
    assert "HARTNETT" not in real_output.upper()
    assert "1556 Camp" not in real_output.upper().title()


def test_address_of_property_is_filled_by_the_picker(real_output):
    assert real_output.count('id="premises"') == 1
    assert re.search(r'Address of property<span class="blank fixed" id="premises"', real_output)
    assert "Which apartment is this application for?" in real_output


def test_every_blank_in_the_source_is_drawn(real_output):
    source = SOURCE_PATH.read_text(encoding="utf-8")
    assert real_output.count('<span class="blank fixed"') == len(re.findall(r"_{2,}", source))


def test_child_checkboxes_are_boxes_not_brackets(real_output):
    assert real_output.count('<span class="box"></span>') == 3
    assert "[ ]" not in real_output


def test_the_arbitration_steps_are_a_list(real_output):
    steps = re.search(r'<ul class="steps">(.*?)</ul>', real_output, re.S).group(1)
    assert steps.count("<li>") == 5
    assert "La. R.S. 9:4201" in steps


def test_the_font_is_embedded(real_output):
    assert "data:font/woff2;base64," in real_output


def test_a_missing_address_blank_fails_the_build(gen):
    broken = SOURCE_PATH.read_text(encoding="utf-8").replace("Address of property", "Property")
    with pytest.raises(SystemExit, match="Address of property"):
        gen.generate(broken)


def test_generated_file_on_disk_matches_a_fresh_run(gen, real_output):
    assert gen.OUTPUT.read_text(encoding="utf-8") == real_output


def test_the_page_script_parses(real_output, tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    for index, script in enumerate(re.findall(r"<script>(.*?)</script>", real_output, re.S)):
        path = tmp_path / f"script{index}.js"
        path.write_text(script, encoding="utf-8")
        result = subprocess.run([node, "--check", str(path)], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
