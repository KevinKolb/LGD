"""Public rental applications, and the news a manager posts."""
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
    """Not validated against known managers - it's whatever the applicant
    typed, e.g. an address that isn't in accounts.json at all."""
    payload = {**APPLICATION_PAYLOAD, "property_interest": "some address I saw on Zillow"}
    response = client.post("/api/applications", json=payload, auth=None)
    assert response.status_code == 201


def test_submit_application_defaults_to_no_roommates(client) -> None:
    response = client.post("/api/applications", json=APPLICATION_PAYLOAD, auth=None)
    assert response.status_code == 201

    body = client.get("/api/applications", auth=ADMIN).json()
    assert body["applications"][0]["roommates"] == []


def test_submit_application_accepts_roommates(client) -> None:
    payload = {
        **APPLICATION_PAYLOAD,
        "roommates": [
            {"name": "Sam Roommate", "email": "sam@example.com"},
            {"name": "Alex Roommate", "email": "alex@example.com"},
        ],
    }
    response = client.post("/api/applications", json=payload, auth=None)
    assert response.status_code == 201

    body = client.get("/api/applications", auth=ADMIN).json()
    assert body["applications"][0]["roommates"] == payload["roommates"]


def test_submit_application_rejects_a_roommate_with_a_bad_email(client) -> None:
    payload = {
        **APPLICATION_PAYLOAD,
        "roommates": [{"name": "Sam Roommate", "email": "not-an-email"}],
    }
    response = client.post("/api/applications", json=payload, auth=None)
    assert response.status_code == 422


def test_submit_application_rejects_more_than_ten_roommates(client) -> None:
    payload = {
        **APPLICATION_PAYLOAD,
        "roommates": [
            {"name": f"Roommate {i}", "email": f"roommate{i}@example.com"}
            for i in range(11)
        ],
    }
    response = client.post("/api/applications", json=payload, auth=None)
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Reviewing applications (admin-only - property_interest is free text, not a
# manager id, so there's no way to scope an application to one manager)
# ---------------------------------------------------------------------------

def test_list_applications_requires_authentication(client) -> None:
    client.post("/api/applications", json=APPLICATION_PAYLOAD, auth=None)
    assert client.get("/api/applications", auth=None).status_code == 401


def test_list_applications_is_refused_to_a_tenant(client) -> None:
    assert client.get("/api/applications", auth=TENANT1).status_code == 404


def test_list_applications_is_refused_to_a_manager(client) -> None:
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
# Posting news (manager/admin)
# ---------------------------------------------------------------------------

def test_post_news_requires_authentication(client) -> None:
    response = client.post(
        "/api/news",
        json={"manager_id": "lgd", "headline": "Hi", "article": "Details."},
        auth=None,
    )
    assert response.status_code == 401


def test_post_news_is_refused_to_a_tenant(client) -> None:
    response = client.post(
        "/api/news",
        json={"manager_id": "lgd", "headline": "Hi", "article": "Details."},
        auth=TENANT1,
    )
    assert response.status_code == 404


def test_a_manager_can_post_news_for_their_own_manager(client) -> None:
    response = client.post(
        "/api/news",
        json={"manager_id": "lgd", "headline": "Pool closed", "article": "For repairs this week."},
        auth=STEVE,
    )
    assert response.status_code == 201


def test_a_manager_cannot_post_news_for_another_manager(client) -> None:
    response = client.post(
        "/api/news",
        json={"manager_id": "robertson", "headline": "Hi", "article": "Details."},
        auth=STEVE,
    )
    assert response.status_code == 403


def test_admin_can_post_news_for_any_manager(client) -> None:
    response = client.post(
        "/api/news",
        json={"manager_id": "robertson", "headline": "Hi", "article": "Details."},
        auth=ADMIN,
    )
    assert response.status_code == 201


def test_post_news_rejects_a_missing_headline(client) -> None:
    response = client.post(
        "/api/news",
        json={"manager_id": "lgd", "headline": "", "article": "Details."},
        auth=STEVE,
    )
    assert response.status_code == 422


def test_news_created_at_is_recorded_in_central_time(client) -> None:
    """Every other created_at in this app is UTC - news is a deliberate
    one-off, recorded in Central time (America/Chicago) instead."""
    client.post(
        "/api/news",
        json={"manager_id": "lgd", "headline": "Hi", "article": "Details."},
        auth=STEVE,
    )
    body = client.get("/api/news", auth=STEVE).json()
    created_at = body["news"][0]["created_at"]
    # Central time is UTC-6 (CST) or UTC-5 (CDT) - never +00:00/Z like the
    # UTC timestamps used everywhere else in this app.
    assert created_at.endswith("-06:00") or created_at.endswith("-05:00")


# ---------------------------------------------------------------------------
# Reading news (manager/admin)
# ---------------------------------------------------------------------------

def test_list_news_requires_authentication(client) -> None:
    assert client.get("/api/news", auth=None).status_code == 401


def test_list_news_is_refused_to_a_tenant(client) -> None:
    assert client.get("/api/news", auth=TENANT1).status_code == 404


def test_a_manager_sees_only_their_own_news(client) -> None:
    client.post(
        "/api/news",
        json={"manager_id": "lgd", "headline": "LGD news", "article": "..."},
        auth=STEVE,
    )
    client.post(
        "/api/news",
        json={"manager_id": "robertson", "headline": "Robertson news", "article": "..."},
        auth=GAY,
    )

    body = client.get("/api/news", auth=STEVE).json()

    assert [n["headline"] for n in body["news"]] == ["LGD news"]


def test_admin_sees_every_managers_news(client) -> None:
    client.post(
        "/api/news",
        json={"manager_id": "lgd", "headline": "LGD news", "article": "..."},
        auth=STEVE,
    )
    client.post(
        "/api/news",
        json={"manager_id": "robertson", "headline": "Robertson news", "article": "..."},
        auth=GAY,
    )

    body = client.get("/api/news", auth=ADMIN).json()

    assert {n["headline"] for n in body["news"]} == {"LGD news", "Robertson news"}


# ---------------------------------------------------------------------------
# Tenant accounts are kept out of the manager dashboard and its API
# ---------------------------------------------------------------------------

def test_tenant_cannot_reach_the_manager_dashboard(client) -> None:
    assert client.get("/manager/", auth=TENANT1).status_code == 404


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
