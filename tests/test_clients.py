"""Logins linked to several clients (the user, 2026-10-02): migration 008."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SQL = (ROOT / "supabase" / "migrations" / "008_clients.sql").read_text(encoding="utf-8")


def test_the_link_table_is_locked_to_the_browser():
    assert "create table if not exists public.person_clients" in SQL
    assert "alter table public.person_clients enable row level security;" in SQL
    assert "revoke all on public.person_clients from anon, authenticated;" in SQL


def test_a_login_switches_only_to_a_client_it_is_linked_to():
    switch = SQL[SQL.index("create or replace function public.set_current_client"):]
    switch = switch[:switch.index("$fn$;")]
    assert "where pc.person_id = caller.id and pc.manager_id = client" in switch
    assert "update public.people p set manager_id = client where p.id = caller.id;" in switch
    for function in ("list_my_clients()", "set_current_client(text)"):
        assert f"revoke all on function public.{function} from public, anon;" in SQL
        assert f"grant execute on function public.{function} to authenticated;" in SQL


def test_the_clients_names():
    assert "('lgd', 'LGD (Lower Garden District Properties), Inc.', '', '')" in SQL
    assert "('robertson', 'Orange Street, Inc.', '', '')" in SQL


def test_lists_show_only_the_current_client_even_to_an_admin():
    lists = SQL[SQL.index("Lists show the client being worked in"):]
    assert lists.count("and p.manager_id is not distinct from caller.manager_id") == 2
    assert "caller.is_admin or p.manager_id" not in lists


def test_the_picker_is_only_on_staff_pages_and_only_for_several_clients():
    home = (ROOT / "shared" / "home.js").read_text(encoding="utf-8")
    assert 'if (list.length < 2 || !header.hasAttribute("data-client-picker")) return;' in home
    for page, picker in (("manager", True), ("admin", True), ("applicant", False), ("resident", False)):
        html = (ROOT / page / "index.html").read_text(encoding="utf-8")
        assert ("<header data-client-picker" in html) is picker, page


def test_the_name_is_momandpop_until_a_client_is_known():
    home = (ROOT / "shared" / "home.js").read_text(encoding="utf-8")
    assert 'const BRAND = "momandpop.com";' in home
    assert "const name = (client && client.name) || BRAND;" in home
    for page in ("applicant", "resident", "manager", "admin", "login"):
        html = (ROOT / page / "index.html").read_text(encoding="utf-8")
        assert '<p class="company" data-client>momandpop.com</p>' in html, page
    assert "<h1 data-client>momandpop.com</h1>" in (ROOT / "index.html").read_text(encoding="utf-8")


def test_the_legal_pages_are_for_managers():
    for page in ("legal_review.html", "legal_research.html"):
        html = (ROOT / "manager" / page).read_text(encoding="utf-8")
        head = html[:html.index("</head>")]
        assert head.index('<script src="../shared/auth.js">') < head.index('<script src="../shared/staff-gate.js">'), page
    gate = (ROOT / "shared" / "staff-gate.js").read_text(encoding="utf-8")
    assert 'auth.requireRole(["manager", "admin"])' in gate


def test_manager_and_admin_are_one_credential():
    """The user, 2026-10-02: "combine manager and admin into one credential
    ... current admin page is accessible through a gear button on manager
    page"."""
    manager = (ROOT / "manager" / "index.html").read_text(encoding="utf-8")
    admin = (ROOT / "admin" / "index.html").read_text(encoding="utf-8")
    home = (ROOT / "shared" / "home.js").read_text(encoding="utf-8")
    assert '<header data-client-picker data-gear="admin/">' in manager
    assert '<header data-client-picker data-up="manager/">' in admin
    assert 'auth.requireRole(["manager", "admin"])' in admin
    assert 'gear.title = "Settings";' in home
    sql = (ROOT / "supabase" / "migrations" / "009_managers_are_admins.sql").read_text(encoding="utf-8")
    assert "update public.people set is_manager = true where is_admin and not is_manager;" in sql
    assert "not (caller.is_manager or caller.is_admin)" in sql


def test_a_welcome_under_every_title_and_no_login_on_home():
    """The user, 2026-10-02: "no login on home page, only logoff if
    necessary. put a generic welcome message under page title, personalized
    if login"."""
    home = (ROOT / "shared" / "home.js").read_text(encoding="utf-8")
    assert 'welcome.textContent = signedInHere() ? "" : "Welcome.";' in home
    assert '"Welcome back, " + first + "."' in home
    assert 'if (bar && header.hasAttribute("data-no-home")) bar.hidden = !signedInHere();' in home
    manager = (ROOT / "manager" / "index.html").read_text(encoding="utf-8")
    assert 'document.getElementById("whoami").textContent = greeting' not in manager
