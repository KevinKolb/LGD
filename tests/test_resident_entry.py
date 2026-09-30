"""Resident Entry (the user, 2026-09-30): a temporary manager section to
put residents in apartments for the rent register - more than one per
unit, and nothing required but the apartment."""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import GAY, STEVE, TENANT1

ROOT = Path(__file__).resolve().parent.parent
MANAGER_PAGE = ROOT / "manager" / "index.html"
MIGRATION = ROOT / "supabase" / "migrations" / "007_resident_entry.sql"


def add(client, auth=STEVE, **values):
    return client.post("/api/residents", json={"address": "1364 Camp St.", "unit": "2", **values}, auth=auth)


def residents(client, auth=STEVE, month=None):
    query = f"?month={month}" if month else ""
    return client.get(f"/api/residents{query}", auth=auth).json()["residents"]


def test_only_the_apartment_is_needed(client) -> None:
    response = add(client)
    assert response.status_code == 200
    assert response.json()["resident"]["full_name"] == "Resident"
    assert [(r["address"], r["unit"], r["full_name"]) for r in residents(client)] == [
        ("1364 Camp St.", "2", "Resident")]


def test_more_than_one_resident_per_unit(client) -> None:
    add(client, first_name="Ann", last_name="Lee")
    add(client, first_name="Bo", phone="504.555.0199")
    listed = residents(client)
    assert sorted(r["full_name"] for r in listed) == ["Ann Lee", "Bo"]
    assert {r["unit"] for r in listed} == {"2"}
    assert [r["phone"] for r in listed if r["full_name"] == "Bo"] == ["(504) 555-0199"]


def test_a_house_needs_no_unit(client) -> None:
    add(client, address="1534 Camp St.", unit="", first_name="Hal")
    assert [(r["address"], r["unit"]) for r in residents(client)] == [("1534 Camp St.", "")]


def test_lease_dates_decide_the_register_month(client) -> None:
    add(client, first_name="Ann", lease_start="2026-10-01")
    assert residents(client, month="2026-09") == []
    assert [r["full_name"] for r in residents(client, month="2026-10")] == ["Ann"]


def test_an_applicant_becomes_the_resident_rather_than_a_second_person(client) -> None:
    client.post("/api/applicants", json={"email": "jane@x.com", "address": "1558 Camp St.", "unit": "B"},
                auth=STEVE)
    add(client, address="1558 Camp St.", unit="B", email="JANE@x.com")
    assert [r["email"] for r in residents(client)] == ["jane@x.com"]
    assert [a["email"] for a in client.get("/api/applicants", auth=STEVE).json()["applicants"]] == ["jane@x.com"]


def test_edit_and_remove(client) -> None:
    person = add(client, first_name="Ann").json()["resident"]
    edited = add(client, person_id=person["id"], unit="3", first_name="Ann", last_name="Lee-Park",
                 lease_end="2027-09-30").json()["resident"]
    assert (edited["full_name"], edited["unit"]) == ("Ann Lee-Park", "3")
    assert client.delete(f"/api/residents/{person['id']}", auth=STEVE).status_code == 200
    assert residents(client) == []


@pytest.mark.parametrize("values, reason", [
    ({"address": " "}, "Pick the apartment."),
    ({"email": "nope"}, "That email address does not look right."),
    ({"phone": "555"}, "The phone number needs at least 10 digits."),
    ({"lease_start": "2026-02-30"}, "A lease date does not look right."),
    ({"lease_start": "2026-10-01", "lease_end": "2026-09-01"}, "The lease cannot end before it starts."),
])
def test_bad_details_are_refused_with_a_reason(client, values, reason) -> None:
    response = add(client, **values)
    assert response.status_code == 422
    assert response.json()["detail"] == reason


def test_other_companies_and_residents_are_kept_out(client) -> None:
    person = add(client, first_name="Ann").json()["resident"]
    assert residents(client, auth=GAY) == []
    assert client.delete(f"/api/residents/{person['id']}", auth=GAY).status_code == 404
    assert add(client, auth=TENANT1).status_code == 404


def test_the_manager_page_has_the_section_before_the_register() -> None:
    page = MANAGER_PAGE.read_text(encoding="utf-8")
    section = page[page.index('<section id="residents">'):]
    section = section[:section.index("</section>")]
    assert '<span class="step" aria-hidden="true">4</span>' in section and "<h2>Resident Entry</h2>" in section
    assert page.index("<h2>Resident Entry</h2>") < page.index("<h2>Monthly Rent Register</h2>")
    start = page.index('<dialog class="popup wide" id="resident-dialog"')
    popup = page[start:page.index("</dialog>", start)]
    assert popup.count(" required") == 1  # the apartment, and nothing else
    for name in ("first_name", "last_name", "email", "phone"):
        assert f'name="{name}"' in popup
    # Wider, and no lease dates asked for now (the user, 2026-09-30); an
    # edit sends back the dates the resident already has.
    assert '<dialog class="popup wide" id="resident-dialog"' in page
    assert "lease_start" not in popup and "lease_end" not in popup
    assert 'values.lease_start = editing.lease_start || "";' in page
    assert 'window.LGD.auth.rpc("save_resident", values)' in page
    assert 'window.LGD.auth.rpc("remove_resident", { person_id: person.id })' in page


def test_the_migration_checks_the_caller_and_keeps_to_their_company() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "revoke all on function public.save_resident(text, text, text, text, text, text, text, text, text) from public, anon;" in sql
    assert "revoke all on function public.remove_resident(text) from public, anon;" in sql
    assert sql.count("not (caller.is_manager or caller.is_admin)") == 3
    assert "revoke all on function public.lgd_property_id(text, text, text) from public, anon, authenticated;" in sql


def test_a_button_views_the_current_residents() -> None:
    """The user, 2026-09-30: "make a button to view current residents" -
    those whose lease covers this month, or who have no lease dates."""
    page = MANAGER_PAGE.read_text(encoding="utf-8")
    assert 'id="view-residents" aria-pressed="false">View current residents</button>' in page
    assert 'return window.LGD.auth.rpc("list_residents", { month });' in page
