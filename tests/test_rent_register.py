"""The monthly rent register (the user, 2026-09-29), and the applicant
page creating a login only for an email address already on file."""
from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path

from tests.conftest import GAY, STEVE, TENANT1

ROOT = Path(__file__).resolve().parent.parent
REGISTER = ROOT / "manager" / "rent_register.html"
MIGRATIONS = ROOT / "supabase" / "migrations"


def place_resident(client, *, name, email, phone, address, apt, manager_id,
                   lease_start=None, lease_end=None) -> None:
    client.get("/api/applicants", auth=STEVE)  # the app has created its tables by now
    connection = sqlite3.connect(os.environ["LGD_DB_PATH"])
    try:
        connection.execute(
            "INSERT INTO properties (id, manager_id, address, apt, created_at) VALUES (?, ?, ?, ?, 'x')",
            (f"{address}-{apt}", manager_id, address, apt))
        connection.execute(
            "INSERT INTO people (id, full_name, email, phone, property_id, manager_id, is_resident, "
            "lease_start, lease_end, created_at) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, 'x')",
            (name, name, email, phone, f"{address}-{apt}", manager_id, lease_start, lease_end))
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
    assert 'window.LGD.auth.rpc("list_residents", { month })' in page
    assert "api(`/api/residents?month=${month}`)" in page
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


# --- By month (the user, 2026-09-30) -----------------------------------------

def test_the_register_shows_only_residents_whose_lease_covers_the_month(client) -> None:
    """"Mind lease dates if exist": no dates, always shown; dates, only in
    the months they cover."""
    place_resident(client, name="Always", email="a@x.com", phone="1", address="1558 Camp St.",
                   apt="A", manager_id="lgd")
    place_resident(client, name="Ended", email="e@x.com", phone="1", address="1558 Camp St.",
                   apt="B", manager_id="lgd", lease_start="2025-09-01", lease_end="2026-08-31")
    place_resident(client, name="Starts", email="s@x.com", phone="1", address="1558 Camp St.",
                   apt="C", manager_id="lgd", lease_start="2026-11-15")

    def names(month):
        return [r["full_name"] for r in client.get(f"/api/residents?month={month}", auth=STEVE).json()["residents"]]
    assert names("2026-08") == ["Always", "Ended"]
    assert names("2026-09") == ["Always"]
    assert names("2026-11") == ["Always", "Starts"]  # starts partway through the month
    assert client.get("/api/residents?month=2026-13", auth=STEVE).status_code == 422


def test_rent_dates_are_recorded_by_month(client) -> None:
    def put(month, received_on, unit="A"):
        return client.put("/api/rent-payments", json={"month": month, "address": "1558 Camp St.",
                                                       "unit": unit, "received_on": received_on}, auth=STEVE)
    assert put("2026-09", "2026-09-03").status_code == 200
    assert put("2026-09", "2026-09-05").json()["payment"]["received_on"] == "2026-09-05"
    put("2026-10", "2026-10-01")
    september = client.get("/api/rent-payments?month=2026-09", auth=STEVE).json()["payments"]
    assert [(p["unit"], p["received_on"]) for p in september] == [("A", "2026-09-05")]
    # An empty date takes it back off; a bad one is refused and changes nothing.
    assert put("2026-09", "2026-02-30").json()["detail"] == "That date does not look right."
    assert client.get("/api/rent-payments?month=2026-09", auth=STEVE).json()["payments"][0]["received_on"] == "2026-09-05"
    put("2026-09", "")
    assert client.get("/api/rent-payments?month=2026-09", auth=STEVE).json()["payments"] == []
    # Another company sees none of it; a resident gets nothing.
    assert client.get("/api/rent-payments?month=2026-10", auth=GAY).json()["payments"] == []
    assert client.get("/api/rent-payments?month=2026-10", auth=TENANT1).status_code == 404


def test_the_register_asks_the_month_first_and_saves_each_date() -> None:
    page = REGISTER.read_text(encoding="utf-8")
    assert '<dialog class="month-popup" id="month-dialog"' in page
    assert '<select id="pick-month"></select>' in page and '<select id="pick-year"></select>' in page
    assert 'Month of <span class="blank" id="month-name"></span>' in page
    assert 'input.type = "date";' in page
    assert "const payment = await savePayment(address, unit, input.value);" in page
    # On paper, the recorded date or the blank cell - never the date box.
    assert "td.received input { display: none; }" in page


def test_the_migration_filters_by_lease_and_locks_the_payments() -> None:
    sql = (MIGRATIONS / "006_rent_register_months.sql").read_text(encoding="utf-8")
    assert "drop function if exists public.list_residents();" in sql
    assert "revoke all on public.rent_payments from anon, authenticated;" in sql
    for function in ("list_residents(text)", "list_rent_payments(text)",
                     "set_rent_payment(text, text, text, text)"):
        assert f"revoke all on function public.{function} from public, anon;" in sql
        assert f"grant execute on function public.{function} to authenticated;" in sql


def test_the_register_is_a_sheet_of_paper_with_back_and_print_only() -> None:
    """The user, 2026-09-30: "look like a piece of paper", then "no home
    button", "no change month button", "show day of the week when
    printing"."""
    page = REGISTER.read_text(encoding="utf-8")
    assert "width: 8.5in;" in page and "min-height: 11in;" in page and "padding: 0.5in;" in page
    buttons = page[page.index('<div class="paper-buttons">'):]
    buttons = buttons[:buttons.index("</div>")]
    assert re.findall(r">([A-Za-z ]+)</a>", buttons) == ["Back", "Save", "Print"]
    assert "<script src=\"../shared/footer.js\"></script>" not in page  # which would add Home
    assert "change-month" not in page
    assert 'const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];' in page
    assert "return `${day}, ${MONTHS[m - 1].slice(0, 3)} ${d}, ${y}`;" in page


LEDGER = ROOT / "manager" / "rent_ledger.html"


def test_the_ledger_records_every_column_of_a_month(client) -> None:
    """The user, 2026-10-02: "Secondary view of rent register should show
    history. Make a modern version of attached. Should be a paid checkbox
    too." One month of the rent card: date, rent, deposit, Paid, comment."""
    def entry(month, **values):
        return client.put("/api/rent-entries", json={"month": month, "address": "1521 St. Andrew St.",
                                                      "unit": "#5", **values}, auth=STEVE)
    saved = entry("2026-01", received_on="2026-01-01", amount="$995", paid=True).json()["entry"]
    assert (saved["amount"], saved["paid"], saved["received_on"]) == ("995", True, "2026-01-01")
    entry("2026-02", amount="995.00", note="late")
    assert entry("2026-03", amount="9x").json()["detail"] == "That amount does not look right."
    year = client.get("/api/rent-history?address=1521 St. Andrew St.&unit=%235&year=2026", auth=STEVE).json()["entries"]
    assert [(e["month"], e["received_on"], e["paid"], e["note"]) for e in year] == [
        ("2026-01", "2026-01-01", True, ""), ("2026-02", None, False, "late")]
    # The register's date box ticks Paid and keeps the rest of the month.
    put = client.put("/api/rent-payments", json={"month": "2026-02", "address": "1521 St. Andrew St.",
                                                  "unit": "#5", "received_on": "2026-02-03"}, auth=STEVE)
    assert put.json()["payment"]["paid"] is True and put.json()["payment"]["note"] == "late"
    # A month with nothing left in it is taken off; another year is its own.
    entry("2026-01")
    year = client.get("/api/rent-history?address=1521 St. Andrew St.&unit=%235&year=2026", auth=STEVE).json()["entries"]
    assert [e["month"] for e in year] == ["2026-02"]
    assert client.get("/api/rent-history?address=1521 St. Andrew St.&unit=%235&year=2025", auth=STEVE).json()["entries"] == []
    # Another company sees none of it; a resident gets nothing.
    assert client.get("/api/rent-history?address=1521 St. Andrew St.&unit=%235&year=2026", auth=GAY).json()["entries"] == []
    assert client.get("/api/rent-history?address=x&year=2026", auth=TENANT1).status_code == 404


def test_the_register_opens_each_apartments_ledger() -> None:
    register = REGISTER.read_text(encoding="utf-8")
    assert "link.href = `rent_ledger.html?${query}`;" in register
    # The manager page links both (the user, 2026-10-02); the ledger opened
    # with no apartment lists the company's apartments to choose from.
    manager = (ROOT / "manager" / "index.html").read_text(encoding="utf-8")
    assert 'href="rent_register.html">Rent register</a>' in manager
    assert 'href="rent_ledger.html">Rent ledgers</a>' in manager
    page = LEDGER.read_text(encoding="utf-8")
    assert 'auth.requireRole(["manager", "admin"])' in page
    assert 'window.LGD.auth.rpc("save_rent_entry", body)' in page
    # Ticking Paid fills an empty date with today and an empty rent with the usual.
    assert "if (!date.value) date.value = todayText;" in page
    assert "if (!amount.value.trim()) amount.value = usualRent(index);" in page
    migration = (ROOT / "supabase" / "migrations" / "013_rent_ledger.sql").read_text(encoding="utf-8")
    assert "update public.rent_payments set paid = true where received_on <> '';" in migration
    assert "grant execute on function public.save_rent_entry(text, text, text, text, text, text, boolean, text) to authenticated;" in migration
