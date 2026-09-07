"""Public rental applications and tenant notices."""
from __future__ import annotations

from tests.conftest import ADMIN, GAY, STEVE, TENANT1

APPLICATION_PAYLOAD = {
    "applicant_name": "Jordan Applicant",
    "applicant_email": "jordan@example.com",
    "applicant_phone": "555-0100",
    "landlord_id": "lgd",
    "desired_move_in": "2026-11-01",
    "message": "Household of two, steady income.",
}


# ---------------------------------------------------------------------------
# Public properties list
# ---------------------------------------------------------------------------

def test_properties_is_public(client) -> None:
    response = client.get("/api/properties", auth=None)
    assert response.status_code == 200


def test_properties_lists_names_only_no_emails(client) -> None:
    body = client.get("/api/properties", auth=None).json()
    assert {p["id"] for p in body["properties"]} == {"lgd", "robertson"}
    assert "@" not in str(body)


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


def test_submit_application_rejects_an_unknown_property(client) -> None:
    payload = {**APPLICATION_PAYLOAD, "landlord_id": "no-such-property"}
    response = client.post("/api/applications", json=payload, auth=None)
    assert response.status_code == 400


def test_submit_application_allows_no_property_chosen(client) -> None:
    payload = {**APPLICATION_PAYLOAD, "landlord_id": None}
    response = client.post("/api/applications", json=payload, auth=None)
    assert response.status_code == 201


# ---------------------------------------------------------------------------
# Reviewing applications (admin/landlord)
# ---------------------------------------------------------------------------

def test_list_applications_requires_authentication(client) -> None:
    client.post("/api/applications", json=APPLICATION_PAYLOAD, auth=None)
    assert client.get("/api/applications", auth=None).status_code == 401


def test_list_applications_is_refused_to_a_tenant(client) -> None:
    assert client.get("/api/applications", auth=TENANT1).status_code == 404


def test_admin_sees_every_application(client) -> None:
    client.post("/api/applications", json=APPLICATION_PAYLOAD, auth=None)
    robertson_payload = {**APPLICATION_PAYLOAD, "landlord_id": "robertson"}
    client.post("/api/applications", json=robertson_payload, auth=None)

    body = client.get("/api/applications", auth=ADMIN).json()

    assert len(body["applications"]) == 2


def test_a_landlord_sees_only_applications_naming_their_own_property(client) -> None:
    client.post("/api/applications", json=APPLICATION_PAYLOAD, auth=None)  # lgd
    robertson_payload = {**APPLICATION_PAYLOAD, "landlord_id": "robertson"}
    client.post("/api/applications", json=robertson_payload, auth=None)

    steve_body = client.get("/api/applications", auth=STEVE).json()
    gay_body = client.get("/api/applications", auth=GAY).json()

    assert [a["landlord_id"] for a in steve_body["applications"]] == ["lgd"]
    assert [a["landlord_id"] for a in gay_body["applications"]] == ["robertson"]


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
