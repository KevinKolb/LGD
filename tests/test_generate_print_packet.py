"""Tests for documents/print/generate_print_packet.py - one page holding the
application, lease and security deposit, with one popup that asks every
question once."""
from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PRINT_DIR = ROOT / "documents" / "print"
MODULE_PATH = PRINT_DIR / "generate_print_packet.py"
MANAGER_PAGE = ROOT / "manager" / "index.html"


@pytest.fixture(scope="module")
def gen():
    spec = importlib.util.spec_from_file_location("generate_print_packet", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def real_output(gen) -> str:
    return gen.generate()


def sections(page: str) -> dict[str, str]:
    return dict(re.findall(r'<section class="document" data-doc="(\w+)">(.*?)</section>', page, re.S))


def test_each_document_is_its_own_generators_body(gen, real_output):
    """Nothing is written twice: each section is the single-document page's
    body, so the two can never say different things."""
    found = sections(real_output)
    assert list(found) == ["application", "lease", "deposit"]
    for key, _, module, source, _ in gen.DOCUMENTS:
        body = module.render_body(source.read_text(encoding="utf-8"))
        assert body.replace('id="premises"', "data-premises") in found[key]
        assert f'<p class="subtitle">{module.SUBTITLE}</p>' in found[key]


def test_every_document_has_a_premises_blank_and_ids_are_unique(real_output):
    assert 'id="premises"' not in real_output
    for key, body in sections(real_output).items():
        assert body.count("data-premises") == 1, key
    ids = re.findall(r'\sid="([^"]+)"', real_output)
    assert len(ids) == len(set(ids))


def test_the_popup_asks_each_question_once(real_output):
    popup = real_output[real_output.index('<div class="picker"'):real_output.index("</form>")]
    assert popup.count('id="picker-property"') == 1
    assert popup.count('id="picker-unit"') == 1
    for target in ("field-rent", "field-term", "field-deposit"):
        assert popup.count(f'data-fills="{target}"') == 1
    # The application's own questions show only while it is ticked.
    assert popup.count('data-for-docs="application"') == 3
    assert "Which documents, and for which apartment?" in popup


def test_the_popup_offers_each_document_as_a_checkbox(real_output):
    boxes = re.findall(r'<input type="checkbox" data-doc-choice value="(\w+)"( checked)?>', real_output)
    assert boxes == [("application", ""), ("lease", " checked"), ("deposit", " checked")]


def test_the_addendum_is_left_out(real_output):
    assert "PLASTER WALLS ADDENDUM" not in real_output


def test_each_document_starts_a_new_sheet(real_output):
    """The wrapper takes no part in layout (so each document paginates as on
    its own page); the page break sits on each later document's heading."""
    assert "section.document { display: contents; }" in real_output
    rule = real_output[real_output.index("section.document:not([hidden]) ~ section.document:not([hidden]) > h1.company {"):]
    assert "break-before: page;" in rule[:rule.index("}")]


def test_all_three_documents_carry_their_own_css(gen, real_output):
    for _, _, module, _, _ in gen.DOCUMENTS:
        assert module.EXTRA_CSS in real_output


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


def test_the_manager_page_links_it():
    page = MANAGER_PAGE.read_text(encoding="utf-8")
    assert 'href="../documents/print/documents_print.html#view"' in page
    assert 'href="../documents/print/documents_print.html"' in page


def test_single_document_pages_have_no_checkboxes():
    for name in ("lease_print.html", "security_deposit_print.html", "application_print.html"):
        page = (PRINT_DIR / name).read_text(encoding="utf-8")
        assert 'type="checkbox" data-doc-choice' not in page
        assert "Which apartment is this" in page
