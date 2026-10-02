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
    assert 'id="open-accepting">Choose properties</button>' in section
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


def test_each_accepting_apartment_is_a_tag_with_an_x_to_stop_it() -> None:
    """The user, 2026-09-30: "must be able to undo accepting applications.
    xs on tags?" """
    page = MANAGER_PAGE.read_text(encoding="utf-8")
    assert 'stop.setAttribute("aria-label", `Stop accepting applications for ${name}`);' in page
    assert "stop.addEventListener(\"click\", () => stopAccepting(apartment, stop));" in page
    assert "open = await saveOpen(rest);" in page


def test_the_manager_page_has_reports() -> None:
    """The user, 2026-09-30: "add a reports coming soon to managers page";
    then 2026-10-02, the first report: every house, its units and residents."""
    page = MANAGER_PAGE.read_text(encoding="utf-8")
    section = page[page.index('<section id="reports">'):]
    section = section[:section.index("</section>")]
    assert '<span class="step" aria-hidden="true">7</span>' in section
    assert "<h2>Reports</h2>" in section and "Coming soon." not in section
    assert 'href="property_report.html">Properties</a>' in section
    report = (MANAGER_PAGE.parent / "property_report.html").read_text(encoding="utf-8")
    # Managers only, the client's own buildings, every unit, vacant marked.
    assert 'auth.requireRole(["manager", "admin"])' in report
    assert "property.manager_id === client" in report
    assert 'return { kind: "vacant", text: "Vacant" };' in report
    assert "https://www.google.com/maps/search/?api=1&query=" in report
    assert ': "https://www.google.com/maps?output=embed&z=17&q=" + encodeURIComponent(where || address);' in report
    # A building's own embed (a Street View the user picked) wins, and
    # addresses sharing a building are one house.
    assert "/^https:[/][/]www[.]google[.]com[/]maps[/]embed[?]/.test(embed" in report
    assert "const name = property.building || property.address;" in report


def test_units_are_named_as_on_paper() -> None:
    """The user, 2026-10-02: "change names of units to match what's on
    paper. #2 (102) for example" - and 011 renames them in the database."""
    import json
    props = {p["address"]: p["units"] for p in json.loads(
        (MANAGER_PAGE.parent.parent / "documents" / "properties.json").read_text(encoding="utf-8"))["properties"]}
    assert props["1364 Camp St."] == ["#1 (101)", "#2 (102)", "#3 (103)", "#4 (201)", "#5 (202)", "#6 (203)", "#7 (204)"]
    assert props["1521 St. Andrew St."] == ["#1", "#2", "#3", "#4", "#5", "#6"]
    migration = (MANAGER_PAGE.parent.parent / "supabase" / "migrations" / "011_unit_names.sql").read_text(encoding="utf-8")
    for table in ("properties", "open_apartments", "rent_payments", "people"):
        assert f"update public.{table} " in migration


def test_anyone_can_ask_whether_applications_are_open(client) -> None:
    """Yes or no, signed out - the applicant page's Apply button."""
    assert client.get("/api/accepting-applications", auth=None).json() == {"accepting": False}
    put(client, STEVE, [CAMP_B])
    assert client.get("/api/accepting-applications", auth=None).json() == {"accepting": True}


def test_the_applicant_page_shows_apply_only_while_some_property_is_open() -> None:
    """The user, 2026-09-30: no Apply button when no property is accepting
    applications - a simple statement instead."""
    page = (ROOT / "applicant" / "index.html").read_text(encoding="utf-8")
    assert '<button type="button" id="choose-apply" hidden>Apply</button>' in page
    assert '<p class="none-open" id="none-open" hidden>No apartments are available at this time.</p>' in page
    # And only while nobody is signed in: Apply makes an account.
    assert 'document.getElementById("choose-apply").hidden = !accepting || signedIn;' in page
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "grant execute on function public.accepting_applications() to anon, authenticated;" in sql
