"""Tests for accounts.json loading, mode selection, and access rules."""
from __future__ import annotations

import json

import pytest

from app import config
from app.auth import hash_password
from app.config import ConfigError, Settings, User, get_settings
from tests.conftest import accounts_document

BASE_ENV = {
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

def test_loads_managers_and_users(load) -> None:
    settings = load()
    assert [manager.id for manager in settings.managers] == ["lgd", "robertson"]
    assert [user.username for user in settings.users] == [
        "kevin", "steve", "gay", "tenant1"
    ]
    assert settings.manager_by_id("lgd").name == "LGD Properties"
    assert settings.manager_by_id("lgd").signer_name == "Pat Manager"


def test_missing_accounts_file_explains_the_fix(tmp_path, monkeypatch) -> None:
    get_settings.cache_clear()
    for key, value in BASE_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("LGD_ACCOUNTS_FILE", str(tmp_path / "absent.json"))
    with pytest.raises(ConfigError, match="app.accounts init"):
        Settings.load()


def test_a_user_without_a_password_is_refused(load) -> None:
    accounts = accounts_document()
    accounts["webusers"][0]["password_hash"] = ""
    with pytest.raises(ConfigError, match="set-password kevin"):
        load(accounts)


def test_a_manager_user_must_name_a_manager(load) -> None:
    accounts = accounts_document()
    del accounts["webusers"][1]["manager_id"]
    with pytest.raises(ConfigError, match="needs a manager_id"):
        load(accounts)


def test_a_manager_user_must_name_a_known_manager(load) -> None:
    accounts = accounts_document()
    accounts["webusers"][1]["manager_id"] = "ghost"
    with pytest.raises(ConfigError, match="unknown manager"):
        load(accounts)


def test_an_unrecognised_role_is_refused(load) -> None:
    accounts = accounts_document()
    accounts["webusers"][1]["role"] = "superuser"
    with pytest.raises(ConfigError, match="expected one of"):
        load(accounts)
def make_user(role: str, manager_id: str | None = None) -> User:
    return User(
        username="u", display_name="U", role=role,
        password_hash="x", manager_id=manager_id,
    )


def test_admin_may_act_for_any_manager() -> None:
    admin = make_user("admin")
    assert admin.is_admin
    assert admin.may_use_manager("lgd")
    assert admin.may_use_manager("robertson")


def test_a_manager_may_act_only_for_their_own() -> None:
    steve = make_user("manager", "lgd")
    assert not steve.is_admin
    assert steve.may_use_manager("lgd")
    assert not steve.may_use_manager("robertson")


def test_managers_for_narrows_the_list(load) -> None:
    settings = load()
    admin = settings.user_by_username("kevin")
    steve = settings.user_by_username("steve")

    assert len(settings.managers_for(admin)) == 2
    assert [manager.id for manager in settings.managers_for(steve)] == ["lgd"]


def test_unknown_username_resolves_to_nothing(load) -> None:
    assert load().user_by_username("mallory") is None


def test_unknown_manager_resolves_to_nothing(load) -> None:
    assert load().manager_by_id("ghost") is None


# ---------------------------------------------------------------------------
# Renames must never lock anyone out
# ---------------------------------------------------------------------------

def test_an_accounts_file_written_before_the_renames_still_loads(tmp_path,
                                                                 monkeypatch) -> None:
    """`accounts.json` is gitignored and holds real password hashes, so it
    cannot be migrated by editing a committed file - an install that predates
    the landlords -> managers and users -> webusers renames has to keep
    working as it is.

    This broke twice while those renames were being made, both times because
    a find-and-replace treated the *old* key names as vocabulary to update
    rather than as historical data. They are frozen strings.
    """
    old = {
        "landlords": [{
            "id": "lgd", "company": "LGD Properties",
            "signer_name": "Pat", "email": "pat@example.com",
        }],
        "users": [{
            "username": "pam", "display_name": "Pam Hartnett",
            "role": "landlord", "landlord_id": "lgd",
            "password_hash": hash_password("a password long enough", iterations=1_000),
        }],
    }
    path = tmp_path / "accounts.json"
    path.write_text(json.dumps(old), encoding="utf-8")

    managers, users = config._load_accounts(path)

    assert [(m.id, m.name) for m in managers] == [("lgd", "LGD Properties")]
    # The role, too: "landlord" is what a pre-rename file stores.
    assert [(u.username, u.role, u.manager_id) for u in users] == [
        ("pam", "manager", "lgd")
    ]
