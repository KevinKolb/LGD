"""The monthly rent register (the user, 2026-09-29), and the applicant
page creating a login only for an email address already on file."""
from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path

from tests.conftest import STEVE, TENANT1

ROOT = Path(__file__).resolve().parent.parent
REGISTER = ROOT / "manager" / "rent_register.html"
MIGRATIONS = ROOT / "supabase" / "migrations"


def place_resident(client, *, name, email, phone, address, apt, manager_id) -> None:
    client.get("/api/applicants", auth=STEVE)  # the app has created its tables by now
    connection = sqlite3.connect(os.environ["LGD_DB_PATH"])
    try:
        connection.execute(
            "INSERT INTO properties (id, manager_id, address, apt, created_at) VALUES (?, ?, ?, ?, 'x')",
            (f"{address}-{apt}", manager_id, address, apt))
        connection.execute(
            "INSERT INTO people (id, full_name, email, phone, property_id, manager_id, is_resident, "
            "created_at) VALUES (?, ?, ?, ?, ?, ?, 1, 'x')",
            (name, name, email, phone, f"{address}-{apt}", manager_id))
        connection.commit()
    finally:
        connection.close()


def test_residents_come_with_their_unit_for_their_own_company(client) -> None:
    place_resident(client, name="Kevin Kolb", email="k@example.com", phone="(504) 555-0100",
                   address="1558 Camp St.", apt="A", manager_id="lgd")
    place_resident(client, name="Other Co", email="o@example.com", phone="1",
                   address="9 Elsewhere", apt="", manager_id="other")
    listed = client.get("/api/residents", auth=STEVE).json()["residents"]
    assert [(r["full_name"], r["address"], r["unit"], r["email"], r["phone"]) for r in listed] == [
        ("Kevin Kolb", "1558 Camp St.", "A", "k@example.com", "(504) 555-0100")]
    assert len(client.get("/api/residents").json()["residents"]) == 2  # the admin sees all
    assert client.get("/api/residents", auth=TENANT1).status_code == 404


def test_the_register_lists_every_unit_with_a_line_for_the_date() -> None:
    page = REGISTER.read_text(encoding="utf-8")
    assert "<th>Apartment</th><th>Tenant</th><th>Email</th><th>Phone</th><th>Date received</th>" in page
    assert 'fetch("../documents/properties.json"' in page
    assert 'window.LGD.auth.rpc("list_residents", {})' in page
    assert 'fetch("/api/residents")' in page
    assert "size: letter;" in page
    # A unit with nobody on file still gets its row; nobody on file is left off.
    assert 'const units = property.units.length ? property.units : [""];' in page
    assert "const stray = people.filter" in page


def test_the_manager_page_links_the_register() -> None:
    page = (ROOT / "manager" / "index.html").read_text(encoding="utf-8")
    assert '<h2>Monthly Rent Register</h2>' in page
    assert 'href="rent_register.html"' in page


def test_the_residents_function_is_for_signed_in_staff_only() -> None:
    sql = (MIGRATIONS / "003_rent_register_and_signup_check.sql").read_text(encoding="utf-8")
    assert "revoke all on function public.list_residents() from public, anon;" in sql
    assert "grant execute on function public.list_residents() to authenticated;" in sql
    assert "not (caller.is_manager or caller.is_admin)" in sql


# --- Creating a login only for an address on file ---------------------------

def test_the_on_file_check_answers_only_yes_or_no() -> None:
    sql = (MIGRATIONS / "003_rent_register_and_signup_check.sql").read_text(encoding="utf-8")
    body = sql[sql.index("create or replace function public.email_on_file(email text)"):]
    body = body[:body.index("$fn$;")]
    assert "returns boolean" in body and "select exists (" in body
    assert "grant execute on function public.email_on_file(text) to anon, authenticated;" in sql


def test_a_signup_not_on_file_gets_no_person() -> None:
    """001's trigger adopts the person on file, and makes none otherwise."""
    sql = (MIGRATIONS / "001_auth_people_rls.sql").read_text(encoding="utf-8")
    trigger = sql[sql.index("create or replace function public.handle_auth_user_confirmed()"):]
    trigger = trigger[:trigger.index("$fn$;")]
    assert "insert into public.people" not in trigger


def test_sign_up_stops_at_an_address_not_on_file() -> None:
    script = (ROOT / "shared" / "auth.js").read_text(encoding="utf-8")
    assert 'const NOT_ON_FILE = "That email address is not yet on file.";' in script
    assert "if (!(await emailOnFile(email))) throw new AuthError(NOT_ON_FILE);" in script


def test_the_applicant_page_starts_with_two_buttons() -> None:
    page = (ROOT / "applicant" / "index.html").read_text(encoding="utf-8")
    main = page[page.index("<main>"):page.index("</main>")]
    visible = main[:main.index('<dialog class="popup" id="apply"')]
    assert re.findall(r"<button[^>]*>([^<]+)</button>", visible) == ["Apply", "Check application status"]


def test_each_button_opens_its_own_popup() -> None:
    """Apply gives an apply popup, Check application status a status popup
    (the user, 2026-09-29)."""
    page = (ROOT / "applicant" / "index.html").read_text(encoding="utf-8")
    assert '<dialog class="popup" id="apply" aria-labelledby="apply-title">' in page
    assert '<dialog class="popup" id="status" aria-labelledby="status-title">' in page
    assert "applyPopup.showModal();" in page
    assert "if (!statusPopup.open) statusPopup.showModal();" in page
    assert '<form id="signup-form" novalidate>' in page[page.index('id="apply"'):page.index('id="status"')]


def test_applying_asks_the_email_first_then_name_and_phone() -> None:
    page = (ROOT / "applicant" / "index.html").read_text(encoding="utf-8")
    assert "if (!(await auth.emailOnFile(address))) throw new auth.AuthError(auth.NOT_ON_FILE);" in page
    details = page[page.index('<div id="signup-step-details" hidden>'):]
    details = details[:details.index('<button type="submit"')]
    assert re.findall(r'<input [^>]*id="signup-(\w+)"', details) == ["first", "last", "phone", "password", "confirm"]
    assert "const details = { first_name: first.value.trim(), last_name: last.value.trim(), phone: phone.value.trim() };" in page
    assert '<script src="../shared/auth.js"></script>' in page


def test_status_needs_a_login_and_is_coming_soon() -> None:
    page = (ROOT / "applicant" / "index.html").read_text(encoding="utf-8")
    assert 'text.textContent = "Sign in to check your application status.";' in page
    assert 'signIn.href = auth.root + "login/?next=" + encodeURIComponent(back);' in page
    assert 'text.textContent = "Coming soon.";' in page
