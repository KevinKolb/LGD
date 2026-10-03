"""Logins linked to several clients (the user, 2026-10-02): migration 008."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SQL = (ROOT / "supabase" / "migrations" / "008_clients.sql").read_text(encoding="utf-8")
ONE = (ROOT / "supabase" / "migrations" / "012_one_people_table.sql").read_text(encoding="utf-8")


def test_the_link_table_is_locked_to_the_browser():
    assert "create table if not exists public.person_clients" in SQL
    assert "alter table public.person_clients enable row level security;" in SQL
    assert "revoke all on public.person_clients from anon, authenticated;" in SQL


def test_everyone_is_in_one_table():
    """The user, 2026-10-02: "combine all supabase people related tables
    into one table ... designate their role or roles in the table". 012
    folds 008's person_clients into people.clients, drops it, and adds a
    roles column in words."""
    assert "alter table public.people add column if not exists clients text[]" in ONE
    assert "drop table if exists public.person_clients;" in ONE
    assert "add column roles text generated always as (" in ONE
    assert "person_clients pc" not in ONE[ONE.index("create or replace function public.list_my_clients"):]


def test_a_login_switches_only_to_a_client_it_is_linked_to():
    switch = ONE[ONE.index("create or replace function public.set_current_client"):]
    switch = switch[:switch.index("$fn$;")]
    assert "if not (client = any (caller.clients)) then" in switch
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


def test_the_picker_is_on_every_page_for_several_clients():
    """The user, 2026-10-02: "managers with multiple companies should be
    able to change companies from any page" - every header page (home.js)
    and every paper page with floating buttons (client-picker.js)."""
    home = (ROOT / "shared" / "home.js").read_text(encoding="utf-8")
    assert "    if (list.length < 2) return;" in home
    assert 'hasAttribute("data-client-picker")' not in home
    paper = (ROOT / "shared" / "client-picker.js").read_text(encoding="utf-8")
    assert "if (!Array.isArray(list) || list.length < 2) return;" in paper
    assert 'auth.rpc("set_current_client", { client: picker.value })' in paper
    for page in ("property_report", "rent_register", "rent_ledger", "legal_review", "legal_research"):
        html = (ROOT / "manager" / f"{page}.html").read_text(encoding="utf-8")
        assert '<script src="../shared/client-picker.js"></script>' in html, page


def test_the_name_is_residential_guide_until_a_client_is_known():
    home = (ROOT / "shared" / "home.js").read_text(encoding="utf-8")
    assert 'const BRAND = "Residential Guide";' in home
    assert "const name = (client && client.name) || BRAND;" in home
    for page in ("applicant", "resident", "manager", "admin", "login"):
        html = (ROOT / page / "index.html").read_text(encoding="utf-8")
        assert '<p class="company" data-client>Residential Guide</p>' in html, page
    assert "<h1 data-client>Residential Guide</h1>" in (ROOT / "index.html").read_text(encoding="utf-8")


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
    assert 'welcome.textContent = "Welcome.";' in home
    # No pop on load (the user, same day): the last welcome is kept and
    # shown at once, and the line holds its height while it is empty.
    assert 'localStorage.getItem(WELCOME_KEY) || "Welcome back."' in home
    assert "localStorage.removeItem(WELCOME_KEY);" in home
    assert "min-height: 1.4em" in home
    account = (ROOT / "shared" / "account.js").read_text(encoding="utf-8")
    assert 'text: stored ? "Logout" : "Login"' in account
    assert '"Welcome back, " + first + label + "."' in home
    # The role is in the welcome, not repeated on the admin page (the
    # user, same day: "Signed in as Kevin Kolb (manager). is duplicative").
    assert '(role === "manager" && held.indexOf("admin") >= 0)' in home
    admin = (ROOT / "admin" / "index.html").read_text(encoding="utf-8")
    assert "(manager).`" not in admin
    assert 'if (bar && header.hasAttribute("data-no-home")) bar.hidden = !signedInHere();' in home
    manager = (ROOT / "manager" / "index.html").read_text(encoding="utf-8")
    assert 'document.getElementById("whoami").textContent = greeting' not in manager


def test_the_resident_page_shows_its_own_companys_contact():
    """The user, 2026-10-02: "separate contact info blocks based on
    company. pull from single company table. edit company table with
    current lgd info, all fields." Migration 014."""
    sql = (ROOT / "supabase" / "migrations" / "014_company_contact.sql").read_text(encoding="utf-8")
    for column in ("contact_name", "phone", "phone_note", "website", "address"):
        assert f"alter table public.managers add column if not exists {column} text;" in sql
    assert "where id = 'lgd';" in sql
    assert "select * into company from public.managers m where m.id = caller.manager_id;" in sql
    assert "grant execute on function public.get_my_company() to authenticated;" in sql
    page = (ROOT / "resident" / "index.html").read_text(encoding="utf-8")
    assert 'auth.rpc("get_my_company", {})' in page
    # No company's details are written into the page any more.
    assert "913.1556" not in page and "Pam and Steve" not in page
