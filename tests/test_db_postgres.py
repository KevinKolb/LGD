"""The Postgres path of app/db.py, exercised against a fake asyncpg pool -
no live network Postgres/Supabase needed."""
from __future__ import annotations

from typing import Any

import pytest

from app import db

pytestmark = pytest.mark.anyio

DSN = "postgres://user:secret@example.supabase.co:5432/postgres"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FakeConnection:
    def __init__(self, store: dict[str, dict[str, Any]],
                 stale_tables: set[str] | None = None) -> None:
        self.store = store
        # Tables that still have their old, pre-migration shape.
        self.stale_tables = stale_tables or set()
        self.dropped: list[str] = []
        self.altered: list[str] = []

    async def fetchval(self, sql: str, *args: Any) -> Any:
        if "information_schema.columns" in sql:
            table, _column = args
            return 1 if table in self.stale_tables else None
        raise AssertionError(f"unexpected fetchval: {sql!r}")

    async def execute(self, sql: str, *args: Any) -> str:
        text = " ".join(sql.split())
        if text.startswith("DROP TABLE"):
            self.dropped.append(text)
            return "DROP TABLE"
        if text.startswith("CREATE TABLE") or "CREATE INDEX" in text:
            return "OK"
        if text.startswith("ALTER TABLE"):
            # db.ADDED_COLUMNS - guarded ADD COLUMN IF NOT EXISTS, run on
            # every pool so a table created before a column existed catches up.
            self.altered.append(text)
            return "ALTER TABLE"
        if text.startswith("INSERT INTO leases"):
            row = dict(zip(db.COLUMNS, args))
            self.store[row["document_id"]] = row
            return "INSERT 0 1"
        if text.startswith("UPDATE leases SET status"):
            status, updated_at, document_id = args
            if document_id not in self.store:
                return "UPDATE 0"
            self.store[document_id]["status"] = status
            self.store[document_id]["updated_at"] = updated_at
            return "UPDATE 1"
        if text.startswith("UPDATE leases SET archive_file"):
            archive_file, completed_at, updated_at, document_id = args
            if document_id not in self.store:
                return "UPDATE 0"
            self.store[document_id].update(
                archive_file=archive_file, completed_at=completed_at,
                updated_at=updated_at,
            )
            return "UPDATE 1"
        raise AssertionError(f"unexpected execute: {sql!r} {args!r}")

    async def fetchrow(self, sql: str, *args: Any) -> dict[str, Any] | None:
        row = self.store.get(args[0])
        return dict(row) if row else None

    async def fetch(self, sql: str, *args: Any) -> list[dict[str, Any]]:
        rows = list(self.store.values())
        if "WHERE manager_id" in sql:
            manager_id, limit = args
            rows = [r for r in rows if r["manager_id"] == manager_id]
        else:
            (limit,) = args
        rows.sort(key=lambda r: r["created_at"], reverse=True)
        return [dict(r) for r in rows[:limit]]


class FakeAcquire:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> FakeConnection:
        return self.connection

    async def __aexit__(self, *exc: Any) -> bool:
        return False


class FakePool:
    def __init__(self, stale_tables: set[str] | None = None) -> None:
        self.store: dict[str, dict[str, Any]] = {}
        self.closed = False
        self.stale_tables = stale_tables or set()
        self.dropped: list[str] = []

    def acquire(self) -> FakeAcquire:
        connection = FakeConnection(self.store, self.stale_tables)
        # Share one list so a test can see what the pool dropped overall.
        connection.dropped = self.dropped
        return FakeAcquire(connection)

    async def close(self) -> None:
        self.closed = True
@pytest.fixture
def fake_pool(monkeypatch) -> FakePool:
    pool = FakePool()

    async def fake_create_pool(dsn: str, *, min_size: int, max_size: int,
                               statement_cache_size: int = 100) -> FakePool:
        return pool

    import asyncpg

    monkeypatch.setattr(asyncpg, "create_pool", fake_create_pool)
    db._pools.clear()
    yield pool
    db._pools.clear()


async def test_init_creates_the_pool(fake_pool) -> None:
    await db.init(DSN)

    assert DSN in db._pools


async def test_init_leaves_already_migrated_tables_alone(fake_pool) -> None:
    """Nothing stale, so nothing should be dropped - this runs on every
    startup, and a live database is on the other end of it."""
    await db.init(DSN)

    assert fake_pool.dropped == []


async def test_init_drops_the_old_shaped_tables(monkeypatch) -> None:
    """A deployment created before this redesign still has the old
    properties/tenants shape, and CREATE TABLE IF NOT EXISTS will not
    reshape it - the same trap that took startup down over users.email."""
    pool = FakePool(stale_tables={"properties", "tenants", "residents"})

    async def fake_create_pool(dsn: str, *, min_size: int, max_size: int,
                               statement_cache_size: int = 100) -> FakePool:
        return pool

    import asyncpg

    monkeypatch.setattr(asyncpg, "create_pool", fake_create_pool)
    db._pools.clear()
    try:
        await db.init(DSN)
    finally:
        db._pools.clear()

    assert pool.dropped == [
        'DROP TABLE "properties"', 'DROP TABLE "tenants"', 'DROP TABLE "residents"',
    ]


async def test_close_pools_closes_and_forgets_every_pool(fake_pool) -> None:
    await db.init(DSN)

    await db.close_pools()

    assert fake_pool.closed is True
    assert db._pools == {}
