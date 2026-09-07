"""The Postgres path of `python -m app.accounts` (init/list/set-password),
exercised against a fake asyncpg connection so the suite never needs a live
network Postgres/Supabase instance - same reasoning as FakePandaDoc."""
from __future__ import annotations

from typing import Any

import pytest

from app import accounts

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class _NullTransaction:
    async def __aenter__(self) -> "_NullTransaction":
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False


class FakeConnection:
    """A tiny in-memory stand-in for the two tables accounts.py touches."""

    def __init__(self) -> None:
        self.landlords: dict[str, dict[str, Any]] = {}
        self.users: dict[str, dict[str, Any]] = {}

    async def execute(self, sql: str, *args: Any) -> None:
        text = " ".join(sql.split())
        if text.startswith("CREATE TABLE"):
            return
        if text.startswith("DELETE FROM users"):
            self.users.clear()
            return
        if text.startswith("DELETE FROM landlords"):
            self.landlords.clear()
            return
        if text.startswith("INSERT INTO landlords"):
            id_, company, signer_name, email = args
            self.landlords[id_] = {
                "id": id_, "company": company,
                "signer_name": signer_name, "email": email,
            }
            return
        if text.startswith("INSERT INTO users"):
            username, display_name, role, landlord_id = args
            self.users[username] = {
                "username": username, "display_name": display_name,
                "role": role, "landlord_id": landlord_id, "password_hash": "",
            }
            return
        if text.startswith("UPDATE users SET password_hash"):
            password_hash, username = args
            self.users[username]["password_hash"] = password_hash
            return
        raise AssertionError(f"unexpected execute: {sql!r} {args!r}")

    async def fetchval(self, sql: str, *args: Any) -> Any:
        if "count(*) FROM landlords" in sql:
            return len(self.landlords)
        raise AssertionError(f"unexpected fetchval: {sql!r}")

    async def fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
        if "FROM landlords" in sql:
            return sorted(self.landlords.values(), key=lambda r: r["id"])
        if "SELECT username FROM users" in sql:
            return [{"username": u} for u in sorted(self.users)]
        if "FROM users" in sql:
            return sorted(self.users.values(), key=lambda r: r["username"])
        raise AssertionError(f"unexpected fetch: {sql!r}")

    async def fetchrow(self, sql: str, *args: Any) -> dict[str, Any] | None:
        if "FROM users WHERE username" in sql:
            return self.users.get(args[0])
        raise AssertionError(f"unexpected fetchrow: {sql!r}")

    def transaction(self) -> _NullTransaction:
        return _NullTransaction()

    async def close(self) -> None:
        return None


@pytest.fixture
def fake_connection(monkeypatch) -> FakeConnection:
    connection = FakeConnection()

    async def fake_connect(dsn: str, *, statement_cache_size: int = 100) -> FakeConnection:
        return connection

    import asyncpg

    monkeypatch.setattr(asyncpg, "connect", fake_connect)
    return connection


DSN = "postgres://user:secret@example.supabase.co:5432/postgres"


async def test_init_writes_starter_landlords_and_users(fake_connection) -> None:
    result = await accounts._pg_init(DSN, force=False)

    assert result == 0
    assert set(fake_connection.landlords) == {"lgd", "robertson"}
    assert set(fake_connection.users) == {"kevin", "pam", "gay"}
    assert all(u["password_hash"] == "" for u in fake_connection.users.values())


async def test_init_refuses_to_clobber_existing_rows_without_force(
    fake_connection
) -> None:
    await accounts._pg_init(DSN, force=False)

    result = await accounts._pg_init(DSN, force=False)

    assert result == 1


async def test_init_with_force_overwrites_existing_rows(fake_connection) -> None:
    await accounts._pg_init(DSN, force=False)
    fake_connection.users["kevin"]["password_hash"] = "some-existing-hash"

    result = await accounts._pg_init(DSN, force=True)

    assert result == 0
    assert fake_connection.users["kevin"]["password_hash"] == ""


async def test_list_reports_landlords_and_password_state(
    fake_connection, capsys
) -> None:
    await accounts._pg_init(DSN, force=False)

    await accounts._pg_list(DSN)

    out = capsys.readouterr().out
    assert "lgd" in out and "LGD Properties" in out
    assert "NO PASSWORD" in out
    assert "kevin" in out and "admin" in out


async def test_set_password_updates_the_stored_hash(
    fake_connection, monkeypatch
) -> None:
    await accounts._pg_init(DSN, force=False)
    passwords = iter(["a very long password", "a very long password"])
    monkeypatch.setattr("getpass.getpass", lambda *_a, **_k: next(passwords))

    result = await accounts._pg_set_password(DSN, "kevin")

    assert result == 0
    assert fake_connection.users["kevin"]["password_hash"] != ""


async def test_set_password_rejects_an_unknown_user(fake_connection) -> None:
    await accounts._pg_init(DSN, force=False)

    result = await accounts._pg_set_password(DSN, "nobody")

    assert result == 1


async def test_set_password_rejects_a_short_password(
    fake_connection, monkeypatch
) -> None:
    await accounts._pg_init(DSN, force=False)
    monkeypatch.setattr("getpass.getpass", lambda *_a, **_k: "short")

    result = await accounts._pg_set_password(DSN, "kevin")

    assert result == 1
    assert fake_connection.users["kevin"]["password_hash"] == ""


async def test_set_password_rejects_a_mismatched_confirmation(
    fake_connection, monkeypatch
) -> None:
    await accounts._pg_init(DSN, force=False)
    passwords = iter(["a very long password", "a different long password"])
    monkeypatch.setattr("getpass.getpass", lambda *_a, **_k: next(passwords))

    result = await accounts._pg_set_password(DSN, "kevin")

    assert result == 1
    assert fake_connection.users["kevin"]["password_hash"] == ""
