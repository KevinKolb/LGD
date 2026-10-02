"""The site's two main colors, chosen on the admin page (the user,
2026-09-30), and shared/theme.js, which puts them on every site page."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.conftest import ADMIN, STEVE

ROOT = Path(__file__).resolve().parent.parent
THEME = ROOT / "shared" / "theme.js"
MIGRATION = ROOT / "supabase" / "migrations" / "005_site_colors.sql"
SITE_PAGES = ["index.html", "applicant/index.html", "resident/index.html", "manager/index.html",
              "admin/index.html", "login/index.html"]


def test_nothing_is_saved_at_first(client) -> None:
    assert client.get("/api/site-colors", auth=None).json() == {"accent": None, "accent2": None}


def test_an_admin_saves_them_and_anyone_reads_them(client) -> None:
    response = client.put("/api/site-colors", json={"accent": "#AA0000", "accent2": "#ffcc00"}, auth=ADMIN)
    assert response.status_code == 200
    assert client.get("/api/site-colors", auth=None).json() == {"accent": "#aa0000", "accent2": "#ffcc00"}


def test_both_empty_goes_back_to_the_defaults(client) -> None:
    client.put("/api/site-colors", json={"accent": "#aa0000", "accent2": "#ffcc00"}, auth=ADMIN)
    client.put("/api/site-colors", json={"accent": "", "accent2": ""}, auth=ADMIN)
    assert client.get("/api/site-colors", auth=None).json() == {"accent": None, "accent2": None}


def test_a_manager_cannot_change_them(client) -> None:
    assert client.put("/api/site-colors", json={"accent": "#aa0000", "accent2": "#ffcc00"},
                      auth=STEVE).status_code == 404


@pytest.mark.parametrize("colors", [{"accent": "red", "accent2": "#ffcc00"},
                                    {"accent": "#aa0000", "accent2": ""}])
def test_a_color_that_is_not_rrggbb_is_refused(client, colors) -> None:
    response = client.put("/api/site-colors", json=colors, auth=ADMIN)
    assert response.status_code == 422
    assert response.json()["detail"] == "Each color needs to look like #1f5d4c."


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
    assert 'return section("Site colors",' in page
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
