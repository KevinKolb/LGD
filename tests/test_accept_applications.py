"""Accept Applications (the user, 2026-09-30): a manager-page section whose
popup shows every apartment, and the manager chooses which ones take
applications."""
from __future__ import annotations

from pathlib import Path

from tests.conftest import GAY, STEVE, TENANT1

ROOT = Path(__file__).resolve().parent.parent
MANAGER_PAGE = ROOT / "manager" / "index.html"
MIGRATION = ROOT / "supabase" / "migrations" / "004_accept_applications.sql"

CAMP_B = {"address": "1558 Camp St.", "unit": "B"}
HOUSE = {"address": "1534 Camp St.", "unit": ""}


def put(client, auth, apartments):
    return client.put("/api/open-apartments", json={"apartments": apartments}, auth=auth)


def test_a_manager_chooses_the_apartments(client) -> None:
    assert client.get("/api/open-apartments", auth=STEVE).json()["apartments"] == []
    saved = put(client, STEVE, [CAMP_B, HOUSE]).json()["apartments"]
    assert [(a["address"], a["unit"]) for a in saved] == [("1534 Camp St.", ""), ("1558 Camp St.", "B")]
    listed = client.get("/api/open-apartments", auth=STEVE).json()["apartments"]
    assert listed == saved


def test_saving_again_keeps_the_open_date_and_closes_what_was_left_out(client) -> None:
    first = {a["address"]: a for a in put(client, STEVE, [CAMP_B, HOUSE]).json()["apartments"]}
    second = put(client, STEVE, [CAMP_B]).json()["apartments"]
    assert [a["address"] for a in second] == ["1558 Camp St."]
    assert second[0]["opened_at"] == first["1558 Camp St."]["opened_at"]


def test_each_company_has_its_own_list(client) -> None:
    put(client, STEVE, [CAMP_B])
    assert client.get("/api/open-apartments", auth=GAY).json()["apartments"] == []


def test_a_resident_cannot_see_or_change_it(client) -> None:
    assert client.get("/api/open-apartments", auth=TENANT1).status_code == 404
    assert put(client, TENANT1, [CAMP_B]).status_code == 404


def test_a_blank_apartment_is_refused(client) -> None:
    response = put(client, STEVE, [{"address": " ", "unit": ""}])
    assert response.status_code == 422
    assert response.json()["detail"] == "One of those apartments does not look right."


def test_the_manager_page_has_the_section_as_step_1() -> None:
    page = MANAGER_PAGE.read_text(encoding="utf-8")
    section = page[page.index('<section id="accepting">'):]
    section = section[:section.index("</section>")]
    assert '<span class="step" aria-hidden="true">1</span>' in section
    assert "<h2>Accept Applications</h2>" in section
    assert 'id="open-accepting">Choose apartments</button>' in section
    start = page.index('<dialog class="popup" id="accepting-dialog"')
    popup = page[start:page.index("</dialog>", start)]
    assert 'id="accepting-choices"' in popup
    # Every apartment from properties.json, a house as one checkbox.
    assert 'const units = property.units.length ? property.units : [""];' in page
    assert 'window.LGD.auth.rpc("set_open_apartments", { apartments })' in page
    assert 'window.LGD.auth.rpc("list_open_apartments", {})' in page


def test_the_migration_locks_the_new_table_and_checks_the_caller() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "alter table public.open_apartments enable row level security;" in sql
    assert "revoke all on public.open_apartments from anon, authenticated;" in sql
    for function in ("list_open_apartments()", "set_open_apartments(json)"):
        assert f"revoke all on function public.{function} from public, anon;" in sql
        assert f"grant execute on function public.{function} to authenticated;" in sql
    assert sql.count("not (caller.is_manager or caller.is_admin)") == 2
    # Always the caller's company, never one the browser sends.
    assert "manager_id text" not in sql.split("set_open_apartments(apartments json)")[1].split("as $fn$")[0]


def test_add_applicant_offers_only_apartments_accepting_applications() -> None:
    """The user, 2026-09-30: "offer only the apartments that are accepting
    applications", and when there are none, "No apartments are available at
    this time." """
    page = MANAGER_PAGE.read_text(encoding="utf-8")
    assert 'document.dispatchEvent(new CustomEvent("lgd-open-apartments", { detail: open }));' in page
    assert 'document.addEventListener("lgd-open-apartments", (event) => {' in page
    assert "if (openUnits(property).length) fields.address.add(" in page
    assert 'say(formMessage, "No apartments are available at this time.", "error");' in page
