"""Tests for accounts.json loading, mode selection, and access rules."""
from __future__ import annotations

import json

import pytest

from app.config import ConfigError, Settings, User, get_settings
from tests.conftest import accounts_document

BASE_ENV = {
    "PANDADOC_MODE": "production",
    "PANDADOC_API_KEY": "production-key",
    "PANDADOC_SANDBOX_API_KEY": "sandbox-key",
    "PANDADOC_TEMPLATE_UUID": "template-uuid",
    "PANDADOC_WEBHOOK_SHARED_KEY": "shared-key",
}


@pytest.fixture
def load(tmp_path, monkeypatch):
    """Write an accounts document and load Settings against it."""

    def loader(accounts: dict | None = None, **env_overrides):
        get_settings.cache_clear()
        path = tmp_path / "accounts.json"
        path.write_text(
            json.dumps(accounts if accounts is not None else accounts_document()),
            encoding="utf-8",
        )
        for key, value in {**BASE_ENV, "LGD_ACCOUNTS_FILE": str(path)}.items():
            monkeypatch.setenv(key, value)
        for key, value in env_overrides.items():
            if value is None:
                monkeypatch.delenv(key, raising=False)
            else:
                monkeypatch.setenv(key, value)
        return Settings.load()

    yield loader
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Accounts file
# ---------------------------------------------------------------------------

def test_loads_landlords_and_users(load) -> None:
    settings = load()
    assert [landlord.id for landlord in settings.landlords] == ["lgd", "robertson"]
    assert [user.username for user in settings.users] == ["kevin", "steve", "gay"]
    assert settings.landlord_by_id("lgd").company == "LGD Properties"
    assert settings.landlord_by_id("lgd").signer_name == "Pat Landlord"


def test_missing_accounts_file_explains_the_fix(tmp_path, monkeypatch) -> None:
    get_settings.cache_clear()
    for key, value in BASE_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("LGD_ACCOUNTS_FILE", str(tmp_path / "absent.json"))
    with pytest.raises(ConfigError, match="app.accounts init"):
        Settings.load()


def test_a_user_without_a_password_is_refused(load) -> None:
    accounts = accounts_document()
    accounts["users"][0]["password_hash"] = ""
    with pytest.raises(ConfigError, match="set-password kevin"):
        load(accounts)


def test_a_landlord_user_must_name_a_landlord(load) -> None:
    accounts = accounts_document()
    del accounts["users"][1]["landlord_id"]
    with pytest.raises(ConfigError, match="needs a landlord_id"):
        load(accounts)


def test_a_landlord_user_must_name_a_known_landlord(load) -> None:
    accounts = accounts_document()
    accounts["users"][1]["landlord_id"] = "ghost"
    with pytest.raises(ConfigError, match="unknown landlord"):
        load(accounts)


def test_an_unrecognised_role_is_refused(load) -> None:
    accounts = accounts_document()
    accounts["users"][1]["role"] = "superuser"
    with pytest.raises(ConfigError, match="expected one of"):
        load(accounts)


def test_duplicate_usernames_are_refused(load) -> None:
    accounts = accounts_document()
    accounts["users"].append({**accounts["users"][1]})
    with pytest.raises(ConfigError, match="duplicate usernames"):
        load(accounts)


def test_a_file_with_no_landlords_is_refused(load) -> None:
    with pytest.raises(ConfigError, match="no landlords"):
        load({"landlords": [], "users": []})


def test_a_file_with_no_users_is_refused(load) -> None:
    accounts = accounts_document()
    accounts["users"] = []
    with pytest.raises(ConfigError, match="nobody could log in"):
        load(accounts)


def test_malformed_json_is_reported_clearly(tmp_path, monkeypatch) -> None:
    get_settings.cache_clear()
    path = tmp_path / "accounts.json"
    path.write_text("{ not json", encoding="utf-8")
    for key, value in BASE_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("LGD_ACCOUNTS_FILE", str(path))
    with pytest.raises(ConfigError, match="not valid JSON"):
        Settings.load()


# ---------------------------------------------------------------------------
# Mode selection
# ---------------------------------------------------------------------------

def test_production_mode_uses_the_production_key(load) -> None:
    settings = load(PANDADOC_MODE="production")
    assert settings.mode == "production"
    assert settings.is_sandbox is False
    assert settings.api_key == "production-key"


def test_sandbox_mode_uses_the_sandbox_key(load) -> None:
    settings = load(PANDADOC_MODE="sandbox")
    assert settings.is_sandbox is True
    assert settings.api_key == "sandbox-key"


def test_mode_defaults_to_sandbox(load) -> None:
    """Spending a production document should never be an accident."""
    settings = load(PANDADOC_MODE=None)
    assert settings.mode == "sandbox"


def test_sandbox_prefers_its_own_template_when_given(load) -> None:
    settings = load(
        PANDADOC_MODE="sandbox", PANDADOC_SANDBOX_TEMPLATE_UUID="sandbox-template"
    )
    assert settings.template_uuid == "sandbox-template"


def test_sandbox_falls_back_to_the_shared_template(load) -> None:
    settings = load(PANDADOC_MODE="sandbox", PANDADOC_SANDBOX_TEMPLATE_UUID=None)
    assert settings.template_uuid == "template-uuid"


def test_an_unknown_mode_is_refused(load) -> None:
    with pytest.raises(ConfigError, match="PANDADOC_MODE"):
        load(PANDADOC_MODE="staging")


def test_a_missing_key_names_the_variable(load) -> None:
    with pytest.raises(ConfigError, match="PANDADOC_SANDBOX_API_KEY"):
        load(PANDADOC_MODE="sandbox", PANDADOC_SANDBOX_API_KEY=None)


# ---------------------------------------------------------------------------
# Access rules
# ---------------------------------------------------------------------------

def make_user(role: str, landlord_id: str | None = None) -> User:
    return User(
        username="u", display_name="U", role=role,
        password_hash="x", landlord_id=landlord_id,
    )


def test_admin_may_act_for_any_landlord() -> None:
    admin = make_user("admin")
    assert admin.is_admin
    assert admin.may_use_landlord("lgd")
    assert admin.may_use_landlord("robertson")


def test_a_landlord_may_act_only_for_their_own() -> None:
    steve = make_user("landlord", "lgd")
    assert not steve.is_admin
    assert steve.may_use_landlord("lgd")
    assert not steve.may_use_landlord("robertson")


def test_landlords_for_narrows_the_list(load) -> None:
    settings = load()
    admin = settings.user_by_username("kevin")
    steve = settings.user_by_username("steve")

    assert len(settings.landlords_for(admin)) == 2
    assert [landlord.id for landlord in settings.landlords_for(steve)] == ["lgd"]


def test_unknown_username_resolves_to_nothing(load) -> None:
    assert load().user_by_username("mallory") is None


def test_unknown_landlord_resolves_to_nothing(load) -> None:
    assert load().landlord_by_id("ghost") is None
