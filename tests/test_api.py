"""End-to-end tests for auth, role scoping, the static pages and the API."""
from __future__ import annotations

import json

import pytest

from tests.conftest import ADMIN, GAY, PASSWORDS, STEVE, TENANT1

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", ["/manager/", "/api/config", "/api/admin/info"])
def test_dashboard_requires_credentials(client, path: str) -> None:
    response = client.get(path, auth=None)
    assert response.status_code == 401
    assert "Basic" in response.headers.get("WWW-Authenticate", "")


def test_wrong_password_is_rejected(client) -> None:
    assert client.get("/api/config", auth=("kevin", "wrong")).status_code == 401


def test_unknown_username_is_rejected(client) -> None:
    assert client.get("/api/config", auth=("mallory", "anything")).status_code == 401


def test_one_users_password_does_not_work_for_another(client) -> None:
    response = client.get("/api/config", auth=("steve", PASSWORDS["gay"]))
    assert response.status_code == 401


@pytest.mark.parametrize("credentials", [ADMIN, STEVE, GAY])
def test_every_configured_user_can_sign_in(client, credentials) -> None:
    assert client.get("/api/config", auth=credentials).status_code == 200


# ---------------------------------------------------------------------------
# Static dashboard
# ---------------------------------------------------------------------------

def test_dashboard_serves_the_paper_lease(client) -> None:
    response = client.get("/manager/")
    assert response.status_code == 200
    assert "Manager Dashboard" in response.text
    assert "Print paper lease" in response.text


def test_favicon_is_served_with_no_login(client) -> None:
    """Browsers request this at the bare domain root before any auth
    context exists, so it must not be behind Basic auth."""
    response = client.get("/favicon.ico", auth=None)
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/vnd.microsoft.icon"


def test_shared_assets_are_served_with_no_login(client) -> None:
    """The public pages (hub, applicant, tenant) load these, so putting
    them behind Basic auth would leave those pages unstyled and
    footerless."""
    css = client.get("/shared/site.css", auth=None)
    assert css.status_code == 200
    assert "footer" in css.text

    script = client.get("/shared/footer.js", auth=None)
    assert script.status_code == 200
    assert "applicant/" in script.text


def test_shared_route_will_not_serve_files_outside_its_directory(client) -> None:
    response = client.get("/shared/../accounts.json", auth=None)
    assert response.status_code == 404


def test_print_route_serves_the_blank_lease(client) -> None:
    """The manager page links to ../documents/print/lease_print.html so that one
    href works both here and on GitHub Pages, which has no /api/."""
    response = client.get("/documents/print/lease_print.html")
    assert response.status_code == 200
    assert "PARKING" in response.text


def test_print_route_requires_a_login(client) -> None:
    assert client.get("/documents/print/lease_print.html", auth=None).status_code == 401


def test_root_serves_a_public_hub_page_with_no_login(client) -> None:
    """Its two role links are relative, not absolute, so that the page
    still works when GitHub Pages serves it under a /LGD/ prefix. The
    Manager and Admin links come from the shared footer script."""
    response = client.get("/", auth=None)
    assert response.status_code == 200
    assert "Resident Portal" in response.text
    assert 'href="applicant/"' in response.text
    assert 'href="resident/"' in response.text
    assert 'src="shared/footer.js"' in response.text


def test_applicant_page_is_public_with_no_login(client) -> None:
    response = client.get("/applicant/", auth=None)
    assert response.status_code == 200
    assert "Rental application" in response.text


def test_tenant_page_no_longer_has_the_application_form(client) -> None:
    response = client.get("/resident/", auth=None)
    assert response.status_code == 200
    assert "Rental application" not in response.text
    assert "Contact" in response.text


@pytest.mark.parametrize("asset", ["..%2f.env", "..%2fapp%2fconfig.py", "nope.html"])
def test_dashboard_will_not_serve_files_outside_its_directory(client, asset) -> None:
    assert client.get(f"/manager/{asset}").status_code == 404


# ---------------------------------------------------------------------------
# Config and role scoping
# ---------------------------------------------------------------------------

def test_admin_sees_both_managers(client) -> None:
    body = client.get("/api/config", auth=ADMIN).json()
    assert body["user"]["is_admin"] is True
    assert body["managers"] == [
        {"id": "lgd", "name": "LGD Properties"},
        {"id": "robertson", "name": "Jamie Reyes Properties"},
    ]


@pytest.mark.parametrize(
    "credentials,expected",
    [
        (STEVE, {"id": "lgd", "name": "LGD Properties"}),
        (GAY, {"id": "robertson", "name": "Jamie Reyes Properties"}),
    ],
)
def test_a_manager_sees_only_their_own(client, credentials, expected) -> None:
    body = client.get("/api/config", auth=credentials).json()
    assert body["user"]["is_admin"] is False
    assert body["managers"] == [expected]


def test_config_never_leaks_email_addresses(client) -> None:
    for credentials in (ADMIN, STEVE, GAY):
        serialized = json.dumps(client.get("/api/config", auth=credentials).json())
        assert "@" not in serialized


# ---------------------------------------------------------------------------
# Admin reference page
# ---------------------------------------------------------------------------

def test_admin_info_is_refused_to_a_manager_user(client) -> None:
    for credentials in (STEVE, GAY):
        assert client.get("/api/admin/info", auth=credentials).status_code == 404


def test_admin_page_itself_still_loads_for_a_manager(client) -> None:
    """The static page is reachable (so the footer link works everywhere),
    even though its data (/api/admin/info, checked above) is admin-only -
    the page's own JS shows "Admins only." for a manager who lands there."""
    response = client.get("/admin/", auth=STEVE)
    assert response.status_code == 200
    assert "Admin reference" in response.text


def test_admin_page_is_refused_to_a_tenant(client) -> None:
    assert client.get("/admin/", auth=TENANT1).status_code == 404


def test_admin_info_requires_authentication(client) -> None:
    assert client.get("/api/admin/info", auth=None).status_code == 401


def test_admin_info_lists_managers_and_users(client) -> None:
    body = client.get("/api/admin/info", auth=ADMIN).json()
    assert {l["id"] for l in body["managers"]} == {"lgd", "robertson"}
    assert {u["username"] for u in body["users"]} == {"kevin", "steve", "gay", "tenant1"}


def test_admin_info_never_leaks_secrets(client) -> None:
    serialized = json.dumps(client.get("/api/admin/info", auth=ADMIN).json())
    assert "password_hash" not in serialized
    assert "SUPABASE_KEY" not in serialized


def test_admin_info_reports_local_backends_by_default(client) -> None:
    body = client.get("/api/admin/info", auth=ADMIN).json()
    assert body["backends"]["records"] == "local SQLite"
    assert body["backends"]["accounts"] == "accounts.json"
    assert "local disk" in body["backends"]["files"]


# ---------------------------------------------------------------------------
# Change own password
# ---------------------------------------------------------------------------

def test_change_password_requires_authentication(client) -> None:
    response = client.post(
        "/api/account/password",
        json={"current_password": "whatever", "new_password": "a new long password"},
        auth=None,
    )
    assert response.status_code == 401


def test_change_password_rejects_the_wrong_current_password(client) -> None:
    response = client.post(
        "/api/account/password",
        json={"current_password": "not-it", "new_password": "a new long password"},
        auth=STEVE,
    )
    assert response.status_code == 400
    assert client.get("/api/config", auth=STEVE).status_code == 200


def test_change_password_rejects_a_too_short_new_password(client) -> None:
    response = client.post(
        "/api/account/password",
        json={"current_password": PASSWORDS["steve"], "new_password": "short"},
        auth=STEVE,
    )
    assert response.status_code == 422


def test_change_password_succeeds_and_takes_effect_immediately(client) -> None:
    new_password = "a brand new long enough password"
    response = client.post(
        "/api/account/password",
        json={"current_password": PASSWORDS["steve"], "new_password": new_password},
        auth=STEVE,
    )
    assert response.status_code == 200

    assert client.get("/api/config", auth=STEVE).status_code == 401
    assert client.get("/api/config", auth=("steve", new_password)).status_code == 200


# ---------------------------------------------------------------------------
# Blank lease (print/download from the dashboard)
# ---------------------------------------------------------------------------

def test_blank_lease_requires_authentication(client) -> None:
    assert client.get("/api/blank-lease", auth=None).status_code == 401


def test_blank_lease_serves_the_generated_print_html(client) -> None:
    """documents/print/lease_print.html is a real, already-generated file in this
    repo; any signed-in user (manager or admin) can fetch it."""
    response = client.get("/api/blank-lease", auth=ADMIN)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "RESIDENTIAL LEASE" in response.text


def test_blank_lease_is_available_to_a_manager_user_too(client) -> None:
    """Not manager-scoped - it's the same blank template
    for everyone, no tenant or manager data in it."""
    assert client.get("/api/blank-lease", auth=STEVE).status_code == 200


def test_blank_lease_404s_clearly_if_never_generated(client, monkeypatch) -> None:
    from app import main

    monkeypatch.setattr(main, "BLANK_LEASE_PATH", main.BLANK_LEASE_PATH.parent / "nope.html")
    response = client.get("/api/blank-lease", auth=ADMIN)
    assert response.status_code == 404
    assert "generate_print_lease.py" in response.json()["detail"]
