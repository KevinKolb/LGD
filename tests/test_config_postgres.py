"""preload_accounts_from_postgres, exercised against a fake asyncpg
connection - no live network Postgres/Supabase needed, same reasoning as
tests/test_accounts_postgres.py."""
from __future__ import annotations

from typing import Any

import pytest

from app import config
from app.config import ConfigError, ROLE_ADMIN, ROLE_MANAGER, Settings

pytestmark = pytest.mark.anyio

BASE_ENV = {
}

DSN = "postgres://user:secret@example.supabase.co:5432/postgres"

MANAGER_ROW = {
    "id": "lgd", "name": "LGD Properties",
    "signer_name": "Pat Manager", "email": "steve-manager@example.com",
}
USER_ROW = {
    "username": "kevin", "display_name": "Kevin Kolb", "role": ROLE_ADMIN,
    "manager_id": None, "password_hash": "some-hash",
    "email": "kevin@example.com", "auth_id": None, "person_id": "person-1",
}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def reset_cache():
    """The accounts cache is a module global - never let one test's
    Postgres rows leak into a later test's local-JSON-file expectations."""
    yield
    config._reset_accounts_cache_for_tests()


class FakeConnection:
    def __init__(self, manager_rows: list[dict[str, Any]],
                user_rows: list[dict[str, Any]]) -> None:
        self._manager_rows = manager_rows
        self._user_rows = user_rows
        self.executed: list[str] = []
        self.updates: list[tuple[Any, ...]] = []

    async def execute(self, sql: str, *args: Any) -> None:
        self.executed.append(" ".join(sql.split()))
        if args:
            self.updates.append(args)

    async def fetch(self, sql: str) -> list[dict[str, Any]]:
        if "FROM managers" in sql:
            return self._manager_rows
        if "FROM webusers" in sql:
            return self._user_rows
        raise AssertionError(f"unexpected fetch: {sql!r}")

    async def close(self) -> None:
        return None


def _patch_connect(monkeypatch, connection: FakeConnection) -> None:
    import asyncpg

    async def fake_connect(dsn: str, *, statement_cache_size: int = 100) -> FakeConnection:
        return connection

    monkeypatch.setattr(asyncpg, "connect", fake_connect)


async def test_preload_populates_the_cache(monkeypatch) -> None:
    _patch_connect(monkeypatch, FakeConnection([MANAGER_ROW], [USER_ROW]))

    await config.preload_accounts_from_postgres(DSN)

    managers, users = config._accounts_cache
    assert [l.id for l in managers] == ["lgd"]
    assert [u.username for u in users] == ["kevin"]


async def test_preload_adds_the_email_column_to_an_older_users_table(monkeypatch) -> None:
    """A deployment created before users.email existed must not be left
    unbootable: selecting a missing column raises and startup dies, which
    is exactly what happened once against the live Supabase project."""
    connection = FakeConnection([MANAGER_ROW], [USER_ROW])
    _patch_connect(monkeypatch, connection)

    await config.preload_accounts_from_postgres(DSN)

    assert "ALTER TABLE webusers ADD COLUMN IF NOT EXISTS email TEXT" in connection.executed


async def test_preload_migrates_the_old_role_names(monkeypatch) -> None:
    """manager -> manager and tenant -> resident, in the stored data."""
    connection = FakeConnection([MANAGER_ROW], [USER_ROW])
    _patch_connect(monkeypatch, connection)

    await config.preload_accounts_from_postgres(DSN)

    assert ("manager", "landlord") in connection.updates
    assert ("resident", "tenant") in connection.updates


async def test_preload_still_accepts_a_pre_rename_role(monkeypatch) -> None:
    """The only authentication this app has is these rows. If a database
    still holds "manager"/"tenant" - because the UPDATE above has not run
    yet, or was rolled back - the load must map them forward rather than
    reject the user and lock everyone out."""
    old_user = {**USER_ROW, "username": "pam", "role": "manager",
                "manager_id": "lgd"}
    _patch_connect(monkeypatch, FakeConnection([MANAGER_ROW], [old_user]))

    await config.preload_accounts_from_postgres(DSN)

    _managers, users = config._accounts_cache
    assert users[0].role == "manager"


async def test_settings_load_reads_the_cache_instead_of_json(
    monkeypatch
) -> None:
    _patch_connect(monkeypatch, FakeConnection([MANAGER_ROW], [USER_ROW]))
    await config.preload_accounts_from_postgres(DSN)
    for key, value in BASE_ENV.items():
        monkeypatch.setenv(key, value)
    # No LGD_ACCOUNTS_FILE set, and no accounts.json needs to exist -
    # proof that Settings.load() never touches the JSON file once the
    # Postgres cache is populated.
    monkeypatch.delenv("LGD_ACCOUNTS_FILE", raising=False)

    settings = Settings.load()

    assert [l.id for l in settings.managers] == ["lgd"]
    assert [u.username for u in settings.users] == ["kevin"]


async def test_settings_load_prefers_database_url_for_db_path(
    monkeypatch
) -> None:
    _patch_connect(monkeypatch, FakeConnection([MANAGER_ROW], [USER_ROW]))
    await config.preload_accounts_from_postgres(DSN)
    for key, value in BASE_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("DATABASE_URL", DSN)
    monkeypatch.setenv("LGD_DB_PATH", "leases.db")

    settings = Settings.load()

    assert settings.db_path == DSN


async def test_preload_rejects_a_user_pointing_at_an_unknown_manager(
    monkeypatch
) -> None:
    bad_user = {**USER_ROW, "role": ROLE_MANAGER, "manager_id": "no-such-manager"}
    _patch_connect(monkeypatch, FakeConnection([MANAGER_ROW], [bad_user]))

    with pytest.raises(ConfigError):
        await config.preload_accounts_from_postgres(DSN)


async def test_preload_rejects_no_managers(monkeypatch) -> None:
    _patch_connect(monkeypatch, FakeConnection([], [USER_ROW]))

    with pytest.raises(ConfigError):
        await config.preload_accounts_from_postgres(DSN)
