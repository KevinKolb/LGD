"""The site's two main colors, chosen on the admin page (the user,
2026-09-30), and shared/theme.js, which puts them on every site page."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.conftest import TENANT1, ADMIN, STEVE, GAY

ROOT = Path(__file__).resolve().parent.parent
THEME = ROOT / "shared" / "theme.js"
MIGRATION = ROOT / "supabase" / "migrations" / "005_site_colors.sql"
SITE_PAGES = ["index.html", "applicant/index.html", "resident/index.html", "manager/index.html",
              "admin/index.html", "login/index.html"]


def test_nothing_is_saved_at_first(client) -> None:
    assert client.get("/api/site-colors", auth=STEVE).json() == {"accent": None, "accent2": None}


def test_signed_out_there_are_no_colors_to_read(client) -> None:
    """Every page is gray while signed out, so nothing asks."""
    assert client.get("/api/site-colors", auth=None).status_code == 401


def test_each_company_has_its_own_colors(client) -> None:
    """The user, 2026-10-02: "separate colors by company, settings only
    apply to current company" - LGD's manager saves LGD's, Orange Street's
    keep theirs."""
    response = client.put("/api/site-colors", json={"accent": "#AA0000", "accent2": "#ffcc00"}, auth=STEVE)
    assert response.status_code == 200
    assert client.get("/api/site-colors", auth=STEVE).json() == {"accent": "#aa0000", "accent2": "#ffcc00"}
    assert client.get("/api/site-colors", auth=TENANT1).json() == {"accent": "#aa0000", "accent2": "#ffcc00"}
    assert client.get("/api/site-colors", auth=GAY).json() == {"accent": None, "accent2": None}
    client.put("/api/site-colors", json={"accent": "#d2601a", "accent2": "#f4a261"}, auth=GAY)
    assert client.get("/api/site-colors", auth=GAY).json() == {"accent": "#d2601a", "accent2": "#f4a261"}
    assert client.get("/api/site-colors", auth=STEVE).json() == {"accent": "#aa0000", "accent2": "#ffcc00"}


def test_both_empty_goes_back_to_the_defaults_for_that_company_only(client) -> None:
    client.put("/api/site-colors", json={"accent": "#aa0000", "accent2": "#ffcc00"}, auth=STEVE)
    client.put("/api/site-colors", json={"accent": "#d2601a", "accent2": "#f4a261"}, auth=GAY)
    client.put("/api/site-colors", json={"accent": "", "accent2": ""}, auth=STEVE)
    assert client.get("/api/site-colors", auth=STEVE).json() == {"accent": None, "accent2": None}
    assert client.get("/api/site-colors", auth=GAY).json() == {"accent": "#d2601a", "accent2": "#f4a261"}


def test_a_manager_can_change_them_and_a_tenant_cannot(client) -> None:
    """Manager and admin are one credential since 2026-10-02 (the user)."""
    assert client.put("/api/site-colors", json={"accent": "#aa0000", "accent2": "#ffcc00"},
                      auth=TENANT1).status_code in (403, 404)


def test_a_login_with_no_company_cannot_save_colors(client) -> None:
    response = client.put("/api/site-colors", json={"accent": "#aa0000", "accent2": "#ffcc00"}, auth=ADMIN)
    assert response.status_code == 422
    assert response.json()["detail"] == "Your login is not filed under a company."


@pytest.mark.parametrize("colors", [{"accent": "red", "accent2": "#ffcc00"},
                                    {"accent": "#aa0000", "accent2": ""}])
def test_a_color_that_is_not_rrggbb_is_refused(client, colors) -> None:
    response = client.put("/api/site-colors", json=colors, auth=STEVE)
    assert response.status_code == 422
    assert response.json()["detail"] == "Each color needs to look like #1f5d4c."


def test_supabase_keeps_them_on_each_company(client) -> None:
    sql = (ROOT / "supabase" / "migrations" / "010_colors_by_company.sql").read_text(encoding="utf-8")
    assert "alter table public.managers add column if not exists accent text;" in sql
    assert "where m.id = caller.manager_id;" in sql
    theme = THEME.read_text(encoding="utf-8")
    assert 'const CACHE = "lgd-site-colors:" + clientId();' in theme
    assert 'Authorization: "Bearer " + token,' in theme


@pytest.mark.parametrize("page", SITE_PAGES)
def test_every_site_page_loads_the_colors_before_it_paints(page) -> None:
    text = (ROOT / page).read_text(encoding="utf-8")
    prefix = "../" * page.count("/")
    head = text[:text.index("</head>")]
    assert f'<script src="{prefix}shared/theme.js"></script>' in head
    # After the page's own scheme script, before its stylesheet can paint.
    assert head.index("shared/theme.js") < head.index("<style>")


def test_theme_uses_the_same_supabase_project_as_auth() -> None:
    auth = (ROOT / "shared" / "auth.js").read_text(encoding="utf-8")
    theme = THEME.read_text(encoding="utf-8")
    for name in ("SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY"):
        pattern = rf'const {name} = "([^"]+)";'
        assert re.search(pattern, auth).group(1) == re.search(pattern, theme).group(1)
    assert "sb_secret" not in theme


def test_the_admin_page_has_the_section() -> None:
    page = (ROOT / "admin" / "index.html").read_text(encoding="utf-8")
    assert 'return section(company ? `Colors for ${company}` : "Company colors",' in page
    assert 'window.LGD.auth.rpc("set_site_colors", body)' in page
    assert 'colorsSection("api")' in page and 'colorsSection("supabase")' in page


def test_the_migration_lets_only_an_admin_write() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "revoke all on public.site_settings from anon, authenticated;" in sql
    assert "grant execute on function public.get_site_colors() to anon, authenticated;" in sql
    assert "revoke all on function public.set_site_colors(text, text) from public, anon;" in sql
    assert "if caller.id is null or not caller.is_admin then" in sql


def test_the_admin_page_tells_a_missing_app_from_a_refusal() -> None:
    """On GitHub Pages /api/admin/info is GitHub's own 404 page; only the
    FastAPI app's JSON 404 means "not an admin". Every 404 used to say
    "Admins only." - to the live site's admins too."""
    page = (ROOT / "admin" / "index.html").read_text(encoding="utf-8")
    assert 'const fromApp = (response.headers.get("content-type") || "").includes("json");' in page
    assert "if (response.status === 404 && fromApp) {" in page


def test_the_admin_page_always_says_what_happened() -> None:
    """Never left on "Loading…" or a bare "Admins only.": who is signed in,
    with which roles, when turned away; and any failure in words (the user,
    2026-09-30: "admin page is still blank")."""
    page = (ROOT / "admin" / "index.html").read_text(encoding="utf-8")
    body = page[page.index("async function explainWithoutBackend(app) {"):]
    assert "} catch (error) {" in body[:body.index("function signOutButton")]
    assert "with the role${who.roles.length > 1 ? \"s\" : \"\"}: ${who.role_label}." in page
    assert "this login has no record on file yet" in page
    assert 'if (app.textContent.trim() === "Loading…") {' in page


def test_signed_out_pages_are_black_white_and_gray():
    """The user, 2026-10-02: "black white and gray on home page no login.
    enable colors site wide when user logs in" - theme.js, on the home page
    again, grays every page while no session is stored."""
    theme = (ROOT / "shared" / "theme.js").read_text(encoding="utf-8")
    assert 'const GRAYS = { accent: "#222222", accent2: "#cfcfcf" };' in theme
    signed_out = theme[theme.index("if (!signedIn()) {"):theme.index("apply(cached());")]
    assert 'style.setProperty("--accent", GRAYS.accent);' in signed_out
    assert "return;" in signed_out  # no fetching, no admin colors
    page = (ROOT / "index.html").read_text(encoding="utf-8")
    assert '<script src="shared/theme.js"></script>' in page
    assert "theme-orange" not in page and "lgd-org" not in page


def test_each_company_has_its_own_address_and_mail() -> None:
    """The user, 2026-10-03: mail to the domain forwarded to an address set
    on the admin page (018), then "on admin page we need to pick a unique
    url stem. https://lgd.residentialguide.app will be for LGD" (019)."""
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    sql = (root / "supabase" / "migrations" / "019_subdomains.sql").read_text(encoding="utf-8")
    assert "create unique index if not exists managers_subdomain on public.managers (subdomain);" in sql
    assert "update public.managers set subdomain = 'lgd' where id = 'lgd' and subdomain is null;" in sql
    assert "grant execute on function public.client_by_subdomain(text) to anon, authenticated;" in sql
    # Only the Email Worker, with the secret key, reads where mail goes.
    assert "revoke all on function public.mail_forward_target(text) from public, anon, authenticated;" in sql
    assert "grant execute on function public.mail_forward_target(text) to service_role;" in sql
    assert "clean like '%residentialguide.app'" in sql
    admin = (root / "admin" / "index.html").read_text(encoding="utf-8")
    assert 'store(stemSave, "set_subdomain", { subdomain: stem.value },' in admin
    assert 'store(forwardSave, "set_mail_forward", { address: forward.value },' in admin
    assert "smtp.gmail.com, Port: 587" in admin and "include:_spf.google.com" in admin
    email = (root / "cloudflare" / "email-worker.js").read_text(encoding="utf-8")
    assert "await savedAddress(env, message.to);" in email and "await message.forward(to);" in email
    assert "sb_secret_" not in email.replace("sb_secret_...", "")
    web = (root / "cloudflare" / "subdomain-worker.js").read_text(encoding="utf-8")
    assert 'const ORIGIN = "https://residentialguide.app";' in web
    # A page on a company's address names that company, and switches a
    # manager of several companies to it.
    home = (root / "shared" / "home.js").read_text(encoding="utf-8")
    assert "const found = await auth.addressClient();" in home
    assert 'await auth.rpc("set_current_client", { client: addressClient.id });' in home
