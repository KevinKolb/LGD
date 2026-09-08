"""The Postgres path of app/db.py, exercised against a fake asyncpg pool -
no live network Postgres/Supabase needed, same reasoning as FakePandaDoc."""
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
        if "WHERE landlord_id" in sql:
            landlord_id, limit = args
            rows = [r for r in rows if r["landlord_id"] == landlord_id]
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


LEASE_KWARGS = dict(
    document_id="doc-1",
    document_name="123 Main St - Jamie Tenant",
    landlord_id="lgd",
    lessor_name="LGD Properties",
    premises_address="123 Main St",
    tenants=[{"name": "Jamie Tenant", "email": "jamie@example.com"}],
    tenant_email="jamie@example.com",
    signing_url="https://app.pandadoc.com/s/abc",
    signing_url_kind="shared_link",
    status="document.draft",
    monthly_rent="2400",
    term_start="2026-10-01",
    term_end="2027-09-30",
    mode="sandbox",
    created_by="kevin",
)


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
    pool = FakePool(stale_tables={"properties", "tenants"})

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

    assert pool.dropped == ['DROP TABLE "properties"', 'DROP TABLE "tenants"']


async def test_record_and_get_lease_round_trip(fake_pool) -> None:
    await db.record_lease(DSN, **LEASE_KWARGS)

    lease = await db.get_lease(DSN, "doc-1")

    assert lease["document_id"] == "doc-1"
    assert lease["landlord_id"] == "lgd"
    assert lease["tenants"] == [{"name": "Jamie Tenant", "email": "jamie@example.com"}]
    assert lease["archive_file"] is None


async def test_get_lease_returns_none_for_an_unknown_id(fake_pool) -> None:
    result = await db.get_lease(DSN, "no-such-doc")

    assert result is None


async def test_update_status_reports_whether_the_lease_was_known(fake_pool) -> None:
    await db.record_lease(DSN, **LEASE_KWARGS)

    known = await db.update_status(DSN, "doc-1", "document.completed")
    unknown = await db.update_status(DSN, "no-such-doc", "document.completed")

    assert known is True
    assert unknown is False
    lease = await db.get_lease(DSN, "doc-1")
    assert lease["status"] == "document.completed"


async def test_record_archive_sets_the_filename_and_completed_at(fake_pool) -> None:
    await db.record_lease(DSN, **LEASE_KWARGS)

    result = await db.record_archive(DSN, "doc-1", "doc-1.pdf")

    assert result is True
    lease = await db.get_lease(DSN, "doc-1")
    assert lease["archive_file"] == "doc-1.pdf"
    assert lease["completed_at"] is not None


async def test_list_leases_filters_by_landlord(fake_pool) -> None:
    await db.record_lease(DSN, **LEASE_KWARGS)
    await db.record_lease(
        DSN, **{**LEASE_KWARGS, "document_id": "doc-2", "landlord_id": "robertson"}
    )

    only_lgd = await db.list_leases(DSN, landlord_id="lgd")
    everything = await db.list_leases(DSN)

    assert [lease["document_id"] for lease in only_lgd] == ["doc-1"]
    assert {lease["document_id"] for lease in everything} == {"doc-1", "doc-2"}


async def test_close_pools_closes_and_forgets_every_pool(fake_pool) -> None:
    await db.init(DSN)

    await db.close_pools()

    assert fake_pool.closed is True
    assert db._pools == {}
