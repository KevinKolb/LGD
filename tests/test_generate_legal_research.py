"""Tests for manager/generate_legal_research.py.

The research log is markdown that a manager reads as an ordinary page on
this site rather than as a raw file on a code host. The converter handles
only what the log actually uses, so these lock in the constructs it does
support - including the one real bug found while building it: a blank line
between numbered sources closed the <ol>, restarting every entry at "1."
(13 separate lists where the log has 4).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "manager" / "generate_legal_research.py"
SOURCE_PATH = REPO_ROOT / "manager" / "LEGAL_RESEARCH.md"


def _load_module():
    spec = importlib.util.spec_from_file_location("generate_legal_research", MODULE_PATH)
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
# The bug: blank lines between numbered items must not split the list
# ---------------------------------------------------------------------------

def test_a_blank_line_between_numbered_items_keeps_one_list(gen):
    """The log separates numbered sources with a blank line for readability.
    Treating that as the end of the list emitted a fresh <ol> per item, so
    every source rendered as "1." in the browser."""
    _, body = gen.convert("1. First source.\n\n2. Second source.\n\n3. Third source.\n")
    assert body.count("<ol>") == 1
    assert body.count("<li>") == 3


def test_a_paragraph_after_a_list_closes_it(gen):
    """Nothing else would close the list, since blank lines no longer do."""
    _, body = gen.convert("1. A source.\n\nA following paragraph.\n")
    assert body.count("<ol>") == 1
    assert body.index("</ol>") < body.index("<p>")


def test_bullets_and_numbers_do_not_run_into_each_other(gen):
    _, body = gen.convert("- A bullet.\n1. A number.\n")
    assert body.count("<ul>") == 1
    assert body.count("<ol>") == 1
    assert body.index("</ul>") < body.index("<ol>")


def test_an_indented_line_joins_the_item_above_it(gen):
    _, body = gen.convert("1. A source title\n   and its continuation.\n")
    assert "<li>A source title and its continuation.</li>" in body


# ---------------------------------------------------------------------------
# Inline markup
# ---------------------------------------------------------------------------

def test_bold_and_italic_become_real_tags(gen):
    assert gen.inline("**Question:** a *word* here") == (
        "<strong>Question:</strong> a <em>word</em> here"
    )


def test_a_code_span_is_not_reread_as_bold_or_italic(gen):
    """Code spans are held aside first for exactly this: the log quotes
    file paths and glob-ish strings that contain asterisks."""
    assert gen.inline("`a * b ** c`") == "<code>a * b ** c</code>"


def test_an_angle_bracketed_url_becomes_one_anchor(gen):
    assert gen.inline("<https://law.justia.com/x>") == (
        '<a href="https://law.justia.com/x" target="_blank" '
        'rel="noopener">https://law.justia.com/x</a>'
    )


def test_a_bare_url_becomes_an_anchor_without_swallowing_the_sentence_period(gen):
    result = gen.inline("See https://example.com/a.")
    assert result.endswith("</a>.")
    assert result.count("<a href=") == 1


def test_html_in_the_markdown_is_escaped_not_emitted(gen):
    assert gen.inline("<script>x</script>") == "&lt;script&gt;x&lt;/script&gt;"


# ---------------------------------------------------------------------------
# Page structure
# ---------------------------------------------------------------------------

def test_the_h1_becomes_the_page_title_and_is_not_repeated_in_the_body(gen):
    title, body = gen.convert("# Legal Research Log\n\nSome text.\n")
    assert title == "Legal Research Log"
    assert "<h1>" not in body


def test_the_real_log_renders_its_four_source_lists(real_output):
    """A regression guard tied to the actual document: 4 numbered lists,
    not the 13 the blank-line bug produced."""
    assert real_output.count("<ol>") == 4


def test_the_page_carries_the_shared_stylesheet_and_footer(real_output):
    assert '<link rel="stylesheet" href="../shared/site.css">' in real_output
    assert '<script src="../shared/footer.js"></script>' in real_output


def test_the_page_says_where_it_came_from(real_output):
    """So nobody edits the generated HTML by hand."""
    assert "manager/LEGAL_RESEARCH.md" in real_output
    assert "manager/generate_legal_research.py" in real_output


def test_output_is_well_formed_enough_to_have_one_head_and_body(real_output):
    assert real_output.count("<html") == 1
    assert real_output.count("<body>") == 1
    assert real_output.count("</body>") == 1


# ---------------------------------------------------------------------------
# Failure modes: stop rather than silently drop content
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "markdown",
    [
        "| a | b |\n| --- | --- |\n",
        "```\ncode\n```\n",
        "> quoted\n",
    ],
)
def test_unsupported_constructs_raise_rather_than_vanish(gen, markdown):
    with pytest.raises(SystemExit):
        gen.convert(markdown)


def test_generation_is_deterministic(gen):
    text = SOURCE_PATH.read_text(encoding="utf-8")
    assert gen.generate(text) == gen.generate(text)


def test_generated_file_on_disk_matches_a_fresh_run(real_output):
    output_path = REPO_ROOT / "manager" / "legal_research.html"
    assert output_path.read_text(encoding="utf-8") == real_output
