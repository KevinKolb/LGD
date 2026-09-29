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
    assert re.search(r'Address of property</span><span class="blank fixed" id="premises"', real_output)
    assert "Which apartment is this application for?" in real_output


def test_every_blank_in_the_source_is_drawn(real_output):
    source = SOURCE_PATH.read_text(encoding="utf-8")
    assert real_output.count('<span class="blank fixed"') == len(re.findall(r"_{2,}", source))


def test_fields_the_user_removed_stay_removed(real_output):
    """2026-09-28, the user: no marital status, no bank account number, no
    "Child" box (and no age) for other occupants."""
    body = real_output[real_output.index("<body>"):real_output.index('<div class="footer-note">')]
    for gone in ("Marital status", "Account #", "Child", "[ ]"):
        assert gone not in body


def test_field_rows_run_the_full_page_width(real_output):
    """Every short row of fields is a flex row whose blanks share the width
    left over by their labels, so each line ends at the right margin."""
    rows = re.findall(r'<p[^>]*class="field row">(.*?)</p>', real_output)
    assert len(rows) >= 20
    for row in rows:
        assert '<span class="blank fixed"' in row
        assert "flex-grow:" in row
    # The application's own rule, not the phone layout's "body p.field.row".
    css = real_output[real_output.index("\n  p.field.row {"):]
    assert "display: flex;" in css[:css.index("}")]
    assert "min-height: 0.375in;" in css[:css.index("}")]


def test_the_vehicles_section_shows_only_where_there_is_parking(real_output):
    """Lease §21 limits parking to vehicles listed on the application, and
    only 1364 Camp has parking - so the rows are tagged parking=limited and
    the picker hides them everywhere else."""
    rows = re.findall(r'<p data-option="parking=limited"[^>]*>(.*?)</p>', real_output, re.S)
    assert len(rows) == 3
    assert "Vehicles to be parked at the property" in rows[0]
    assert all("Plate #" in row for row in rows[1:])
    assert "(parking=limited)" not in real_output


def test_the_office_fills_rent_term_deposit_and_holding_from_the_popup(gen, real_output):
    for lead, key in gen.OFFICE_FIELDS:
        assert real_output.count(f'data-fill="{key}"') == 1, key
    popup = real_output[real_output.index('<div class="picker"'):real_output.index("</form>")]
    for key in gen.QUESTIONS:
        assert f'id="q-{key}" data-q="{key}"' in popup
    assert popup.count("(optional)") == 4

def test_lessor_not_owner_and_its_agent_not_his(real_output):
    body = real_output[real_output.index("<body>"):real_output.index('<div class="footer-note">')]
    assert "owner" not in body.lower()
    assert "his agent" not in body
    assert "prospective Lessor and/or its agent" in body


def test_there_is_a_credit_check_authorization_with_initials(real_output):
    assert "CREDIT CHECK AUTHORIZATION:" in real_output
    assert "obtain a consumer credit report" in real_output
    assert re.search(r"Applicant&#x27;s initials<span class=\"blank fixed\"", real_output)


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


def test_every_money_label_ends_in_a_dollar_sign(real_output):
    """Formatted the same (the user, 2026-09-29): each amount's label ends
    in "$" before its blank, as "Security deposit $" always did."""
    for label in ("Monthly rental rate $", "Security deposit $", "Monthly rent $", "Monthly salary $"):
        assert f'<span class="label">{label}</span>' in real_output, label


def test_money_boxes_take_only_digits_a_point_and_one_dollar_sign(real_output):
    popup = real_output[real_output.index('<div class="picker"'):real_output.index("</form>")]
    for key in ("rent", "deposit", "holding"):
        assert f'id="q-{key}" data-q="{key}" data-money inputmode="decimal" value="$"' in popup
    # Term of lease is not an amount.
    assert 'id="q-term" data-q="term" data-money' not in popup
    script = real_output[real_output.index('document.querySelectorAll("input[data-money]")'):]
    assert 'before.replace(/[^0-9.]/g, "")' in script
    assert 'var cleaned = "$" + amount;' in script
    # What fills the form drops the "$" - its printed label has one - and
    # groups thousands: "1,200", "1,200.50".
    assert 'value.replace(/^[$]/, "")' in real_output
    assert 'amount.toLocaleString("en-US"' in real_output

def test_the_term_is_months_or_years_never_both(real_output):
    """A whole number and one choice of months or years; filled as
    "12 months" or "1 year"."""
    popup = real_output[real_output.index('<div class="picker"'):real_output.index("</form>")]
    assert 'id="q-term" data-q="term" data-term inputmode="numeric">' in popup
    assert ('<select id="q-term-unit" aria-label="Months or years">'
            '<option value="month">months</option><option value="year">years</option></select>') in popup
    assert 'input.value.replace(/[^0-9]/g, "")' in real_output
    assert 'termCount + " " + termUnit + (termCount === 1 ? "" : "s")' in real_output

def test_the_deposit_follows_the_rent_until_edited(real_output):
    """Leaving the rent box copies its amount into the deposit box, which
    stays editable: it follows the rent only while empty or still holding
    the amount last copied (the user, 2026-09-29)."""
    assert 'id="q-deposit" data-q="deposit" data-money inputmode="decimal" value="$" data-follows="q-rent"' in real_output
    script = real_output[real_output.index('document.querySelectorAll("[data-follows]")'):]
    assert 'if (box.value === empty || box.value === copied)' in script
