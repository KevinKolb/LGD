"""End-to-end tests for auth, role scoping, lease creation, webhook and archive."""
from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from tests.conftest import ADMIN, GAY, PASSWORDS, SHARED_KEY, STEVE, TEMPLATE_UUID

LEASE_PAYLOAD = {
    "lessor_id": "lgd",
    "premises_address": "1556 Camp Street, Unit B",
    "tenants": [
        {"first_name": "Jane", "last_name": "Doe", "email": "jane@example.com"}
    ],
    "term_start": "2026-10-01",
    "term_end_month": "2027-09",
    "monthly_rent": "1850",
    "security_deposit": "1850",
    "occupants": "Jane Doe",
    "utilities_excluded": "water",
    "execution_city": "New Orleans",
    "execution_date": "2026-09-15",
}
ROBERTSON_PAYLOAD = {**LEASE_PAYLOAD, "lessor_id": "robertson"}


def sign(body: bytes, key: str = SHARED_KEY) -> str:
    return hmac.new(key.encode(), body, hashlib.sha256).hexdigest()


def webhook_body(document_id: str = "doc-1",
                 status: str | None = "document.completed",
                 event: str = "document_state_changed") -> bytes:
    data: dict[str, object] = {"id": document_id}
    if status:
        data["status"] = status
    return json.dumps([{"event": event, "data": data}]).encode()


def post_webhook(client, body: bytes, signature: str | None = None):
    signature = signature if signature is not None else sign(body)
    return client.post(
        f"/webhooks/pandadoc?signature={signature}", content=body, auth=None
    )


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", ["/landlord/", "/api/config", "/api/leases"])
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


def test_webhook_is_not_behind_basic_auth(client) -> None:
    """PandaDoc cannot send Basic credentials; it authenticates by HMAC."""
    assert post_webhook(client, json.dumps([]).encode()).status_code == 200


# ---------------------------------------------------------------------------
# Static dashboard
# ---------------------------------------------------------------------------

def test_dashboard_serves_the_lease_maker(client) -> None:
    response = client.get("/landlord/")
    assert response.status_code == 200
    assert "LGD Lease Maker" in response.text
    assert "Approved potential tenant" in response.text


def test_root_redirects_to_the_dashboard(client) -> None:
    response = client.get("/", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert response.headers["location"] == "/landlord/"


@pytest.mark.parametrize("asset", ["..%2f.env", "..%2fapp%2fconfig.py", "nope.html"])
def test_dashboard_will_not_serve_files_outside_its_directory(client, asset) -> None:
    assert client.get(f"/landlord/{asset}").status_code == 404


# ---------------------------------------------------------------------------
# Config and role scoping
# ---------------------------------------------------------------------------

def test_admin_sees_both_landlords(client) -> None:
    body = client.get("/api/config", auth=ADMIN).json()
    assert body["user"]["is_admin"] is True
    assert body["landlords"] == [
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
def test_a_landlord_sees_only_their_own(client, credentials, expected) -> None:
    body = client.get("/api/config", auth=credentials).json()
    assert body["user"]["is_admin"] is False
    assert body["landlords"] == [expected]


def test_config_never_leaks_email_addresses(client) -> None:
    for credentials in (ADMIN, STEVE, GAY):
        serialized = json.dumps(client.get("/api/config", auth=credentials).json())
        assert "@" not in serialized


def test_landlord_cannot_create_a_lease_for_the_other_landlord(
    client, fake_pandadoc
) -> None:
    response = client.post("/api/leases", json=ROBERTSON_PAYLOAD, auth=STEVE)
    assert response.status_code == 403
    assert fake_pandadoc.created == []


def test_landlord_cannot_preview_for_the_other_landlord(client) -> None:
    assert client.post(
        "/api/leases/preview", json=ROBERTSON_PAYLOAD, auth=STEVE
    ).status_code == 403


def test_admin_may_create_for_either_landlord(client, fake_pandadoc) -> None:
    assert client.post("/api/leases", json=LEASE_PAYLOAD, auth=ADMIN).status_code == 201
    fake_pandadoc.next_document_id = "doc-2"
    assert client.post(
        "/api/leases", json=ROBERTSON_PAYLOAD, auth=ADMIN
    ).status_code == 201


def test_unknown_landlord_is_rejected(client) -> None:
    response = client.post("/api/leases", json={**LEASE_PAYLOAD, "lessor_id": "nope"})
    assert response.status_code == 400
    assert "Unknown landlord" in response.json()["detail"]


def test_each_landlord_sees_only_their_own_leases(client, fake_pandadoc) -> None:
    client.post("/api/leases", json=LEASE_PAYLOAD, auth=STEVE)
    fake_pandadoc.next_document_id = "doc-2"
    client.post("/api/leases", json=ROBERTSON_PAYLOAD, auth=GAY)

    steve_leases = client.get("/api/leases", auth=STEVE).json()["leases"]
    gay_leases = client.get("/api/leases", auth=GAY).json()["leases"]
    admin_leases = client.get("/api/leases", auth=ADMIN).json()["leases"]

    assert [lease["landlord_id"] for lease in steve_leases] == ["lgd"]
    assert [lease["landlord_id"] for lease in gay_leases] == ["robertson"]
    assert len(admin_leases) == 2


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

def test_preview_spends_no_document(client, fake_pandadoc) -> None:
    response = client.post("/api/leases/preview", json=LEASE_PAYLOAD)
    assert response.status_code == 200
    assert fake_pandadoc.created == []
    assert fake_pandadoc.sent == []


def test_preview_shows_company_as_lessor_and_person_as_signer(client) -> None:
    """The lease's signature line reads "Lessor/Agent"."""
    body = client.post("/api/leases/preview", json=LEASE_PAYLOAD).json()

    tokens = {token["name"]: token["value"] for token in body["tokens"]}
    assert tokens["Lessor.Name"] == "LGD Properties"
    assert tokens["Rent.Discounted"] == "1,800.00"
    assert tokens["Term.StartYear"] == "26"
    assert body["recipients"][0] == {
        "role": "Lessor",
        "name": "Pat Landlord",
        "email": "steve-landlord@example.com",
    }


def test_preview_records_nothing(client) -> None:
    client.post("/api/leases/preview", json=LEASE_PAYLOAD)
    assert client.get("/api/leases").json()["leases"] == []


def test_preview_requires_authentication(client) -> None:
    response = client.post("/api/leases/preview", json=LEASE_PAYLOAD, auth=None)
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Lease creation
# ---------------------------------------------------------------------------

def test_creating_a_lease_returns_a_signing_link(client, fake_pandadoc) -> None:
    body = client.post("/api/leases", json=LEASE_PAYLOAD).json()
    assert body["document_id"] == "doc-1"
    assert body["signing_url"] == fake_pandadoc.shared_link
    assert body["signing_url_kind"] == "shared_link"
    assert body["tenants"] == [{"name": "Jane Doe", "email": "jane@example.com"}]
    assert body["is_sandbox"] is False


def test_creation_sends_the_right_template_and_recipients(client, fake_pandadoc) -> None:
    client.post("/api/leases", json=ROBERTSON_PAYLOAD)

    created = fake_pandadoc.created[0]
    assert created["template_uuid"] == TEMPLATE_UUID
    assert created["metadata"]["landlord_id"] == "robertson"

    tokens = {token["name"]: token["value"] for token in created["tokens"]}
    assert tokens["Lessor.Name"] == "Jamie Reyes Properties"
    assert created["recipients"][0]["email"] == "gay-landlord@example.com"


def test_document_is_sent_silently_by_default(client, fake_pandadoc) -> None:
    client.post("/api/leases", json=LEASE_PAYLOAD)
    assert fake_pandadoc.sent[0]["silent"] is True


def test_session_link_is_the_fallback_when_no_shared_link_exists(
    client, fake_pandadoc
) -> None:
    fake_pandadoc.shared_link = None
    body = client.post("/api/leases", json=LEASE_PAYLOAD).json()
    assert body["signing_url_kind"] == "session_link"
    assert "session-for-jane@example.com" in body["signing_url"]


def test_invalid_lease_never_reaches_pandadoc(client, fake_pandadoc) -> None:
    bad = {**LEASE_PAYLOAD, "term_end_month": "2026-09"}  # ends before it starts
    assert client.post("/api/leases", json=bad).status_code == 422
    assert fake_pandadoc.created == []


def test_created_lease_appears_in_the_list(client) -> None:
    client.post("/api/leases", json=LEASE_PAYLOAD, auth=STEVE)

    leases = client.get("/api/leases").json()["leases"]
    assert len(leases) == 1
    assert leases[0]["document_id"] == "doc-1"
    assert leases[0]["lessor_name"] == "LGD Properties"
    assert leases[0]["status"] == "document.sent"
    assert leases[0]["term_end"] == "2027-09-30"
    assert leases[0]["mode"] == "production"
    assert leases[0]["created_by"] == "steve"


# ---------------------------------------------------------------------------
# Sandbox mode
# ---------------------------------------------------------------------------

def test_sandbox_mode_is_reported_to_the_dashboard(make_client) -> None:
    with make_client(mode="sandbox") as client:
        body = client.get("/api/config", auth=ADMIN).json()
        assert body["mode"] == "sandbox"
        assert body["is_sandbox"] is True


def test_sandbox_leases_are_recorded_as_sandbox(make_client) -> None:
    with make_client(mode="sandbox") as client:
        body = client.post("/api/leases", json=LEASE_PAYLOAD, auth=ADMIN).json()
        assert body["is_sandbox"] is True
        leases = client.get("/api/leases", auth=ADMIN).json()["leases"]
        assert leases[0]["mode"] == "sandbox"


def test_sandbox_downloads_avoid_the_protected_endpoint(
    make_client, fake_pandadoc
) -> None:
    """download-protected requires a production key and 401s in sandbox."""
    with make_client(mode="sandbox") as client:
        client.post("/api/leases", json=LEASE_PAYLOAD, auth=ADMIN)
        post_webhook(client, webhook_body())
        assert fake_pandadoc.downloads[0]["protected"] is False


def test_production_downloads_use_the_protected_endpoint(client, fake_pandadoc) -> None:
    client.post("/api/leases", json=LEASE_PAYLOAD)
    post_webhook(client, webhook_body())
    assert fake_pandadoc.downloads[0]["protected"] is True


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------

def test_webhook_updates_the_lease_status(client) -> None:
    client.post("/api/leases", json=LEASE_PAYLOAD)
    assert post_webhook(client, webhook_body(status="document.viewed")).status_code == 200
    assert client.get("/api/leases").json()["leases"][0]["status"] == "document.viewed"


def test_webhook_with_a_bad_signature_changes_nothing(client) -> None:
    client.post("/api/leases", json=LEASE_PAYLOAD)
    assert post_webhook(client, webhook_body(), signature="deadbeef").status_code == 403
    assert client.get("/api/leases").json()["leases"][0]["status"] == "document.sent"


def test_webhook_without_a_signature_is_rejected(client) -> None:
    response = client.post("/webhooks/pandadoc", content=webhook_body(), auth=None)
    assert response.status_code == 403


def test_webhook_for_an_unknown_document_is_ignored(client, fake_pandadoc) -> None:
    response = post_webhook(client, webhook_body(document_id="never-seen"))
    assert response.status_code == 200
    # An unknown document must not trigger an archive download.
    assert fake_pandadoc.downloads == []


def test_webhook_accepts_a_bare_object_as_well_as_a_list(client) -> None:
    client.post("/api/leases", json=LEASE_PAYLOAD)
    body = json.dumps(
        {"event": "document_state_changed",
         "data": {"id": "doc-1", "status": "document.viewed"}}
    ).encode()
    assert post_webhook(client, body).status_code == 200
    assert client.get("/api/leases").json()["leases"][0]["status"] == "document.viewed"


def test_webhook_with_malformed_json_but_valid_signature(client) -> None:
    assert post_webhook(client, b"{not json").status_code == 400


# ---------------------------------------------------------------------------
# Archive of executed leases
# ---------------------------------------------------------------------------

def test_completion_archives_the_signed_pdf(client, archive_dir) -> None:
    client.post("/api/leases", json=LEASE_PAYLOAD)
    post_webhook(client, webhook_body(status="document.completed"))

    lease = client.get("/api/leases").json()["leases"][0]
    assert lease["archive_file"] == "doc-1.pdf"
    assert lease["completed_at"]
    assert (archive_dir / "doc-1.pdf").read_bytes().startswith(b"%PDF")


def test_pdf_ready_event_also_archives(client, archive_dir) -> None:
    client.post("/api/leases", json=LEASE_PAYLOAD)
    post_webhook(
        client,
        webhook_body(status=None, event="document_completed_pdf_ready"),
    )
    assert (archive_dir / "doc-1.pdf").is_file()


def test_archived_lease_downloads_as_a_pdf(client) -> None:
    client.post("/api/leases", json=LEASE_PAYLOAD)
    post_webhook(client, webhook_body())

    response = client.get("/api/leases/doc-1/document")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")


def test_download_fetches_on_demand_when_not_yet_archived(
    client, fake_pandadoc, archive_dir
) -> None:
    client.post("/api/leases", json=LEASE_PAYLOAD)
    assert not archive_dir.exists()

    response = client.get("/api/leases/doc-1/document")
    assert response.status_code == 200
    assert fake_pandadoc.downloads
    assert (archive_dir / "doc-1.pdf").is_file()


def test_download_reports_a_pdf_that_is_not_ready(client, fake_pandadoc) -> None:
    fake_pandadoc.pdf_bytes = None  # PandaDoc answered 202
    client.post("/api/leases", json=LEASE_PAYLOAD)

    response = client.get("/api/leases/doc-1/document")
    assert response.status_code == 409
    assert "not ready" in response.json()["detail"]


def test_archiving_is_not_repeated_once_stored(client, fake_pandadoc) -> None:
    client.post("/api/leases", json=LEASE_PAYLOAD)
    post_webhook(client, webhook_body())
    assert len(fake_pandadoc.downloads) == 1

    client.get("/api/leases/doc-1/document")
    post_webhook(client, webhook_body())
    assert len(fake_pandadoc.downloads) == 1


def test_a_landlord_cannot_download_the_other_landlords_lease(client) -> None:
    client.post("/api/leases", json=LEASE_PAYLOAD, auth=STEVE)
    post_webhook(client, webhook_body())

    # 404 rather than 403: existence itself is not disclosed.
    assert client.get("/api/leases/doc-1/document", auth=GAY).status_code == 404
    assert client.get("/api/leases/doc-1/document", auth=STEVE).status_code == 200
    assert client.get("/api/leases/doc-1/document", auth=ADMIN).status_code == 200


def test_downloading_an_unknown_lease_is_a_404(client) -> None:
    assert client.get("/api/leases/no-such-doc/document").status_code == 404


def test_download_requires_authentication(client) -> None:
    client.post("/api/leases", json=LEASE_PAYLOAD)
    assert client.get("/api/leases/doc-1/document", auth=None).status_code == 401
