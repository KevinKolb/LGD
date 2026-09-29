"""A manager adds an applicant from the manager page (2026-09-29): first,
last, email and mobile, stored as a person with role "applicant" in the
manager's own company. These cover this app's /api/applicants; the website
does the same through Supabase - see test_the_migration_* below for what
supabase/migrations/002_manager_adds_applicants.sql must keep doing."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.conftest import ADMIN, GAY, STEVE, TENANT1

ROOT = Path(__file__).resolve().parent.parent
MIGRATION = ROOT / "supabase" / "migrations" / "002_manager_adds_applicants.sql"
MANAGER_PAGE = ROOT / "manager" / "index.html"

JANE = {"first_name": " Jane ", "last_name": "Doe", "email": " Jane.Doe@Example.com ",
        "mobile": "504.555.1234"}


def add(client, auth, **changes):
    return client.post("/api/applicants", json={**JANE, **changes}, auth=auth)


def test_a_manager_adds_an_applicant_to_their_own_company(client) -> None:
    response = add(client, STEVE)
    assert response.status_code == 201
    created = response.json()["applicant"]
    assert created["first_name"] == "Jane" and created["last_name"] == "Doe"
    assert created["email"] == "jane.doe@example.com"
    assert created["mobile"] == "(504) 555-1234"
    assert created["has_login"] is False
    listed = client.get("/api/applicants", auth=STEVE).json()["applicants"]
    assert [a["email"] for a in listed] == ["jane.doe@example.com"]


def test_another_company_cannot_see_them_but_an_admin_can(client) -> None:
    add(client, STEVE)
    add(client, GAY, email="bob@other.com", first_name="Bob")
    assert [a["first_name"] for a in client.get("/api/applicants", auth=GAY).json()["applicants"]] == ["Bob"]
    assert sorted(a["first_name"] for a in client.get("/api/applicants", auth=ADMIN).json()["applicants"]) == ["Bob", "Jane"]


def test_the_same_email_is_refused_the_second_time(client) -> None:
    add(client, STEVE)
    response = add(client, STEVE, email="JANE.DOE@example.com")
    assert response.status_code == 422
    assert response.json()["detail"] == "That person is already on the applicant list."


@pytest.mark.parametrize("changes, reason", [
    ({"first_name": "  "}, "First name, last name, email and mobile are all needed."),
    ({"email": "not-an-email"}, "That email address does not look right."),
    ({"mobile": "555-1234"}, "The mobile number needs at least 10 digits."),
])
def test_bad_details_are_refused_with_a_reason(client, changes, reason) -> None:
    response = add(client, STEVE, **changes)
    assert response.status_code == 422
    assert response.json()["detail"] == reason


def test_a_resident_cannot_add_or_list_applicants(client) -> None:
    assert add(client, TENANT1).status_code == 404
    assert client.get("/api/applicants", auth=TENANT1).status_code == 404


def test_a_signed_out_visitor_cannot_add_one(client) -> None:
    assert add(client, None).status_code == 401


# --- The website's side: supabase/migrations/002 ----------------------------
# Checked against a local Postgres with a stand-in auth schema on 2026-09-29:
# anonymous callers are refused, a signed-in applicant cannot add or list,
# each manager sees only their company, and a later signup with the same
# email adopts the record instead of making a second person.

def test_the_migration_only_lets_signed_in_staff_call_it() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    for function in ("create_applicant(text, text, text, text)", "list_applicants(boolean)",
                     "set_applicant_archived(text, boolean)"):
        assert f"revoke all on function public.{function} from public, anon;" in sql
        assert f"grant execute on function public.{function} to authenticated;" in sql
    assert sql.count("not (caller.is_manager or caller.is_admin)") == 3
    assert "security definer" in sql


def test_the_migration_files_applicants_under_the_callers_company() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    body = sql[sql.index("create or replace function public.create_applicant("):]
    body = body[:body.index("$fn$;")]
    assert "is_applicant = true" in body and "is_applicant, created_at" in body
    assert "caller.manager_id" in body
    assert "manager_id text" not in body.split("returns json")[0]  # never a browser-sent company


def test_a_later_login_adopts_the_waiting_person() -> None:
    """Since the merge the login is the person: 001's signup trigger gives
    the waiting row its auth_id instead of making a second person."""
    sql = (MIGRATION.parent / "001_auth_people_rls.sql").read_text(encoding="utf-8")
    trigger = sql[sql.index("create or replace function public.handle_auth_user_confirmed()"):]
    trigger = trigger[:trigger.index("$fn$;")]
    assert "where lower(email) = lower(new.email) and auth_id is null" in trigger


def test_the_manager_page_has_the_applicant_form_as_step_1() -> None:
    page = MANAGER_PAGE.read_text(encoding="utf-8")
    section = page[page.index('<section id="applicants">'):]
    section = section[:section.index("</section>")]
    assert '<span class="step" aria-hidden="true">1</span>' in section
    for name in ("first_name", "last_name", "email", "mobile"):
        assert f'name="{name}"' in section
    assert 'window.LGD.auth.rpc("create_applicant", values)' in page
    assert 'window.LGD.auth.rpc("list_applicants", { archived })' in page


# --- Archiving (the user, 2026-09-29) ---------------------------------------

def archive(client, auth, person_id, archived=True):
    return client.post(f"/api/applicants/{person_id}/archive", json={"archived": archived}, auth=auth)


def test_an_archived_applicant_moves_to_the_archived_list_and_back(client) -> None:
    person = add(client, STEVE).json()["applicant"]
    response = archive(client, STEVE, person["id"])
    assert response.status_code == 200 and response.json()["applicant"]["archived"] is True
    assert client.get("/api/applicants", auth=STEVE).json()["applicants"] == []
    archived = client.get("/api/applicants?archived=true", auth=STEVE).json()["applicants"]
    assert [a["email"] for a in archived] == ["jane.doe@example.com"]

    assert archive(client, STEVE, person["id"], archived=False).status_code == 200
    assert client.get("/api/applicants?archived=true", auth=STEVE).json()["applicants"] == []
    assert len(client.get("/api/applicants", auth=STEVE).json()["applicants"]) == 1


def test_adding_an_archived_applicant_again_brings_them_back(client) -> None:
    person = add(client, STEVE).json()["applicant"]
    archive(client, STEVE, person["id"])
    again = add(client, STEVE)
    assert again.status_code == 201
    assert again.json()["applicant"]["id"] == person["id"]  # the same person, not a second one
    assert again.json()["applicant"]["archived"] is False


def test_another_company_cannot_archive_them(client) -> None:
    person = add(client, STEVE).json()["applicant"]
    response = archive(client, GAY, person["id"])
    assert response.status_code == 404
    assert response.json()["detail"] == "No such applicant."
    assert archive(client, ADMIN, person["id"]).status_code == 200


def test_a_resident_cannot_archive(client) -> None:
    person = add(client, STEVE).json()["applicant"]
    assert archive(client, TENANT1, person["id"]).status_code == 404


# --- Sending them the application -------------------------------------------

def test_the_application_tags_the_applicants_own_blanks_once_each() -> None:
    page = (ROOT / "documents" / "print" / "application_print.html").read_text(encoding="utf-8")
    tagged = re.findall(r'<span class="label">([^<]+)</span><span class="blank fixed" data-applicant="(\w+)"', page)
    assert tagged == [("Name of Applicant", "name"), ("Telephone #", "phone"), ("Email", "email")]


def test_the_popup_fills_them_only_for_the_applicant_the_address_names() -> None:
    page = (ROOT / "documents" / "print" / "documents_print.html").read_text(encoding="utf-8")
    assert 'new URLSearchParams(window.location.search).get("applicant")' in page
    assert 'window.sessionStorage.getItem("lgd-applicant")' in page
    assert "stored.id === applicantId" in page


def test_each_applicant_row_offers_application_email_and_archive() -> None:
    page = MANAGER_PAGE.read_text(encoding="utf-8")
    assert '"../documents/print/documents_print.html?docs=application&applicant="' in page
    assert 'sessionStorage.setItem("lgd-applicant"' in page
    assert "mailto:${encodeURIComponent(person.email)}" in page
    assert 'actionButton("Archive", () => archive(person, true, actions))' in page
    assert 'actionButton("Restore", () => archive(person, false, actions))' in page
    assert 'id="toggle-archived"' in page
    assert 'window.LGD.auth.rpc("list_applicants", { archived })' in page
    assert 'window.LGD.auth.rpc("set_applicant_archived", { person_id: person.id, archived })' in page
