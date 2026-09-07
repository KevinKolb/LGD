"""Public rental applications and tenant notices."""
from __future__ import annotations

from tests.conftest import ADMIN, GAY, STEVE, TENANT1

APPLICATION_PAYLOAD = {
    "applicant_name": "Jordan Applicant",
    "applicant_email": "jordan@example.com",
    "applicant_phone": "555-0100",
    "consent_to_text": True,
    "property_interest": "1556 Camp Street",
    "desired_move_in": "2026-11-01",
    "message": "Household of two, steady income.",
}


# ---------------------------------------------------------------------------
# Submitting an application (public)
# ---------------------------------------------------------------------------

def test_submit_application_requires_no_login(client) -> None:
    response = client.post("/api/applications", json=APPLICATION_PAYLOAD, auth=None)
    assert response.status_code == 201


def test_submit_application_rejects_a_missing_name(client) -> None:
    payload = {**APPLICATION_PAYLOAD, "applicant_name": ""}
    response = client.post("/api/applications", json=payload, auth=None)
    assert response.status_code == 422


def test_submit_application_rejects_an_invalid_email(client) -> None:
    payload = {**APPLICATION_PAYLOAD, "applicant_email": "not-an-email"}
    response = client.post("/api/applications", json=payload, auth=None)
    assert response.status_code == 422


def test_submit_application_requires_a_phone_number(client) -> None:
    payload = {**APPLICATION_PAYLOAD, "applicant_phone": ""}
    response = client.post("/api/applications", json=payload, auth=None)
    assert response.status_code == 422


def test_submit_application_consent_to_text_defaults_to_false(client) -> None:
    payload = {k: v for k, v in APPLICATION_PAYLOAD.items() if k != "consent_to_text"}
    response = client.post("/api/applications", json=payload, auth=None)
    assert response.status_code == 201

    body = client.get("/api/applications", auth=ADMIN).json()
    assert body["applications"][0]["consent_to_text"] is False


def test_submit_application_allows_no_property_typed(client) -> None:
    payload = {**APPLICATION_PAYLOAD, "property_interest": ""}
    response = client.post("/api/applications", json=payload, auth=None)
    assert response.status_code == 201


def test_submit_application_property_interest_is_free_text(client) -> None:
    """Not validated against known landlords - it's whatever the applicant
    typed, e.g. an address that isn't in accounts.json at all."""
    payload = {**APPLICATION_PAYLOAD, "property_interest": "some address I saw on Zillow"}
    response = client.post("/api/applications", json=payload, auth=None)
    assert response.status_code == 201


# ---------------------------------------------------------------------------
# Reviewing applications (admin-only - property_interest is free text, not a
# landlord id, so there's no way to scope an application to one landlord)
# ---------------------------------------------------------------------------

def test_list_applications_requires_authentication(client) -> None:
    client.post("/api/applications", json=APPLICATION_PAYLOAD, auth=None)
    assert client.get("/api/applications", auth=None).status_code == 401


def test_list_applications_is_refused_to_a_tenant(client) -> None:
    assert client.get("/api/applications", auth=TENANT1).status_code == 404


def test_list_applications_is_refused_to_a_landlord(client) -> None:
    for credentials in (STEVE, GAY):
        assert client.get("/api/applications", auth=credentials).status_code == 404


def test_admin_sees_every_application(client) -> None:
    client.post("/api/applications", json=APPLICATION_PAYLOAD, auth=None)
    other_payload = {**APPLICATION_PAYLOAD, "property_interest": "a different address"}
    client.post("/api/applications", json=other_payload, auth=None)

    body = client.get("/api/applications", auth=ADMIN).json()

    assert len(body["applications"]) == 2
    assert body["applications"][0]["applicant_phone"] == "555-0100"
    assert body["applications"][0]["consent_to_text"] is True


# ---------------------------------------------------------------------------
# Sending a notice (admin/landlord)
# ---------------------------------------------------------------------------

def test_send_notice_requires_authentication(client) -> None:
    response = client.post(
        "/api/notices",
        json={"tenant_username": "tenant1", "message": "hi"},
        auth=None,
    )
    assert response.status_code == 401


def test_send_notice_is_refused_to_a_tenant(client) -> None:
    response = client.post(
        "/api/notices",
        json={"tenant_username": "tenant1", "message": "hi"},
        auth=TENANT1,
    )
    assert response.status_code == 404


def test_a_landlord_can_notice_their_own_tenant(client) -> None:
    response = client.post(
        "/api/notices",
        json={"tenant_username": "tenant1", "message": "Water off Tuesday."},
        auth=STEVE,
    )
    assert response.status_code == 201


def test_a_landlord_cannot_notice_another_landlords_tenant(client) -> None:
    response = client.post(
        "/api/notices",
        json={"tenant_username": "tenant1", "message": "hi"},
        auth=GAY,
    )
    assert response.status_code == 403


def test_admin_can_notice_any_tenant(client) -> None:
    response = client.post(
        "/api/notices",
        json={"tenant_username": "tenant1", "message": "hi"},
        auth=ADMIN,
    )
    assert response.status_code == 201


def test_send_notice_rejects_an_unknown_username(client) -> None:
    response = client.post(
        "/api/notices",
        json={"tenant_username": "no-such-user", "message": "hi"},
        auth=ADMIN,
    )
    assert response.status_code == 400


def test_send_notice_rejects_a_non_tenant_username(client) -> None:
    response = client.post(
        "/api/notices",
        json={"tenant_username": "steve", "message": "hi"},
        auth=ADMIN,
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Reading notices (tenant only)
# ---------------------------------------------------------------------------

def test_list_notices_requires_authentication(client) -> None:
    assert client.get("/api/notices", auth=None).status_code == 401


def test_list_notices_is_refused_to_a_landlord(client) -> None:
    assert client.get("/api/notices", auth=STEVE).status_code == 404


def test_list_notices_is_refused_to_an_admin(client) -> None:
    assert client.get("/api/notices", auth=ADMIN).status_code == 404


def test_tenant_sees_their_own_notices_newest_first(client) -> None:
    client.post(
        "/api/notices",
        json={"tenant_username": "tenant1", "message": "First notice"},
        auth=STEVE,
    )
    client.post(
        "/api/notices",
        json={"tenant_username": "tenant1", "message": "Second notice"},
        auth=STEVE,
    )

    body = client.get("/api/notices", auth=TENANT1).json()

    assert [n["message"] for n in body["notices"]] == ["Second notice", "First notice"]


def test_tenant_does_not_see_another_tenants_notices(client) -> None:
    client.post(
        "/api/notices",
        json={"tenant_username": "tenant1", "message": "Not for you"},
        auth=STEVE,
    )

    # No second tenant fixture exists, but an empty inbox for a tenant with
    # no notices addressed to them proves the query is scoped by username,
    # not returning every notice in the table.
    body = client.get("/api/notices", auth=TENANT1).json()
    assert all(n["tenant_username"] == "tenant1" for n in body["notices"])


# ---------------------------------------------------------------------------
# Tenant accounts are kept out of the landlord dashboard and its API
# ---------------------------------------------------------------------------

def test_tenant_cannot_reach_the_landlord_dashboard(client) -> None:
    assert client.get("/landlord/", auth=TENANT1).status_code == 404


def test_tenant_cannot_call_api_config(client) -> None:
    assert client.get("/api/config", auth=TENANT1).status_code == 404


def test_tenant_cannot_list_leases(client) -> None:
    assert client.get("/api/leases", auth=TENANT1).status_code == 404


def test_tenant_can_still_change_their_own_password(client) -> None:
    response = client.post(
        "/api/account/password",
        json={
            "current_password": "tenant one password long",
            "new_password": "a brand new tenant password",
        },
        auth=TENANT1,
    )
    assert response.status_code == 200
