"""Lease persistence: SQLite locally, Postgres (e.g. Supabase) in production.

Every public function here takes `db_path` as its first argument, exactly as
before this file supported two backends. Which backend actually runs is
decided purely by what `db_path` looks like:

    "leases.db"                          -> SQLite (a local file)
    "postgres://..." / "postgresql://..." -> Postgres, via asyncpg

This means `app/main.py` never needs to know which backend is active - it
just passes `settings.db_path` through unchanged. The point of the second
backend is Render's free tier: local files there get wiped on every restart,
so a real lease record can't live on local disk if this is ever deployed
there. Postgres (a free Supabase project, in practice) survives restarts;
SQLite is what tests use, and what running this on a laptop always used.
"""
from __future__ import annotations

import asyncio
import json
import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

CENTRAL_TIME = ZoneInfo("America/Chicago")

SCHEMA = """
CREATE TABLE IF NOT EXISTS leases (
    document_id       TEXT PRIMARY KEY,
    document_name     TEXT NOT NULL,
    landlord_id       TEXT NOT NULL,
    lessor_name       TEXT NOT NULL,
    premises_address  TEXT NOT NULL,
    tenants_json      TEXT NOT NULL,
    tenant_email      TEXT NOT NULL,
    signing_url       TEXT,
    signing_url_kind  TEXT,
    status            TEXT NOT NULL,
    monthly_rent      TEXT NOT NULL,
    term_start        TEXT NOT NULL,
    term_end          TEXT NOT NULL,
    mode              TEXT NOT NULL,
    created_by        TEXT NOT NULL,
    archive_file      TEXT,
    completed_at      TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS leases_created_at ON leases (created_at DESC);
CREATE INDEX IF NOT EXISTS leases_landlord ON leases (landlord_id, created_at DESC);

-- Public rental applications, submitted from the tenant page with no login.
-- property_interest is free text, not a landlord id - see ApplicationRequest
-- in app/tenant_portal.py - so these are never landlord-scoped, admin-only.
CREATE TABLE IF NOT EXISTS applications (
    id                  TEXT PRIMARY KEY,
    property_interest   TEXT,
    applicant_name      TEXT NOT NULL,
    applicant_email     TEXT NOT NULL,
    applicant_phone     TEXT NOT NULL,
    consent_to_text     INTEGER NOT NULL DEFAULT 0,
    desired_move_in     TEXT,
    message             TEXT,
    -- Name/email pairs for anyone applying alongside the primary applicant.
    -- Just a household-size hint for now, not yet a separate application
    -- of their own - see app/tenant_portal.py's Roommate docstring.
    roommates_json      TEXT NOT NULL DEFAULT '[]',
    created_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS applications_created_at ON applications (created_at DESC);

-- Free-form messages a landlord/admin sends a specific tenant, shown when
-- that tenant logs in on the tenant page.
CREATE TABLE IF NOT EXISTS notices (
    id               TEXT PRIMARY KEY,
    tenant_username  TEXT NOT NULL,
    message          TEXT NOT NULL,
    created_by       TEXT NOT NULL,
    created_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS notices_tenant ON notices (tenant_username, created_at DESC);

-- Which landlord owns which property address.
CREATE TABLE IF NOT EXISTS properties (
    address   TEXT PRIMARY KEY,
    landlord  TEXT NOT NULL
);

-- Tenant address book (name + mailing address), independent of the
-- tenants_json list embedded in each lease.
CREATE TABLE IF NOT EXISTS tenants (
    full_name  TEXT NOT NULL,
    address    TEXT NOT NULL,
    apt        TEXT,
    city       TEXT NOT NULL DEFAULT 'New Orleans',
    state      TEXT NOT NULL DEFAULT 'LA'
);

-- News a landlord/admin posts, from the landlord dashboard. created_at is
-- recorded in Central time (see _now_central below), unlike every other
-- table here, which records UTC - a deliberate one-off per the user's
-- request, not a general policy change.
CREATE TABLE IF NOT EXISTS news (
    id           TEXT PRIMARY KEY,
    landlord_id  TEXT NOT NULL,
    headline     TEXT NOT NULL,
    article      TEXT NOT NULL,
    created_by   TEXT NOT NULL,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS news_created_at ON news (created_at DESC);
CREATE INDEX IF NOT EXISTS news_landlord ON news (landlord_id, created_at DESC);
"""

APPLICATION_COLUMNS = [
    "id", "property_interest", "applicant_name", "applicant_email",
    "applicant_phone", "consent_to_text", "desired_move_in", "message",
    "roommates_json", "created_at",
]
NOTICE_COLUMNS = ["id", "tenant_username", "message", "created_by", "created_at"]
NEWS_COLUMNS = ["id", "landlord_id", "headline", "article", "created_by", "created_at"]

# Same columns, Postgres syntax (SERIAL/AUTOINCREMENT differences don't apply
# here - document_id is always a real PandaDoc id, never generated).
POSTGRES_SCHEMA = SCHEMA.replace(
    "CREATE INDEX IF NOT EXISTS", "CREATE INDEX IF NOT EXISTS"
)  # identical DDL is valid on both - kept as one constant so a future column
   # change can't accidentally update one schema and not the other.

COLUMNS = [
    "document_id", "document_name", "landlord_id", "lessor_name",
    "premises_address", "tenants_json", "tenant_email", "signing_url",
    "signing_url_kind", "status", "monthly_rent", "term_start", "term_end",
    "mode", "created_by", "archive_file", "completed_at", "created_at",
    "updated_at",
]


def _now() -> str:
    # Microsecond precision, not just seconds: two rows created in quick
    # succession (e.g. two notices sent back to back) still need a distinct,
    # reliably orderable created_at for "ORDER BY created_at DESC" to return
    # them in the right order.
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _now_central() -> str:
    """Like _now(), but in Central time (America/Chicago) rather than UTC -
    only news posts record a timestamp this way, per the user's request.
    Still unambiguous (isoformat keeps the UTC offset, which also correctly
    shifts between CST/CDT on its own), just expressed in Central local
    time instead of UTC."""
    return datetime.now(CENTRAL_TIME).isoformat(timespec="microseconds")


def _is_postgres(db_path: str) -> bool:
    return db_path.startswith("postgres://") or db_path.startswith("postgresql://")


# ---------------------------------------------------------------------------
# SQLite backend (local files - what tests use, and a plain laptop run)
# ---------------------------------------------------------------------------

def _connect(db_path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path, timeout=10.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def _sqlite_init(db_path: str) -> None:
    with _connect(db_path) as connection:
        connection.executescript(SCHEMA)


def _sqlite_insert(db_path: str, row: dict[str, Any]) -> None:
    columns = ", ".join(row)
    placeholders = ", ".join(f":{key}" for key in row)
    with _connect(db_path) as connection:
        connection.execute(
            f"INSERT INTO leases ({columns}) VALUES ({placeholders})", row
        )


def _sqlite_update_status(db_path: str, document_id: str, status: str) -> bool:
    with _connect(db_path) as connection:
        cursor = connection.execute(
            "UPDATE leases SET status = ?, updated_at = ? WHERE document_id = ?",
            (status, _now(), document_id),
        )
        return cursor.rowcount > 0


def _sqlite_get(db_path: str, document_id: str) -> dict[str, Any] | None:
    with _connect(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM leases WHERE document_id = ?", (document_id,)
        ).fetchone()
    if row is None:
        return None
    record = dict(row)
    record["tenants"] = json.loads(record.pop("tenants_json"))
    return record


def _sqlite_record_archive(db_path: str, document_id: str, archive_file: str) -> bool:
    with _connect(db_path) as connection:
        cursor = connection.execute(
            "UPDATE leases SET archive_file = ?, completed_at = ?, updated_at = ? "
            "WHERE document_id = ?",
            (archive_file, _now(), _now(), document_id),
        )
        return cursor.rowcount > 0


def _sqlite_list(db_path: str, limit: int,
                 landlord_id: str | None) -> list[dict[str, Any]]:
    with _connect(db_path) as connection:
        if landlord_id is None:
            rows = connection.execute(
                "SELECT * FROM leases ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM leases WHERE landlord_id = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (landlord_id, limit),
            ).fetchall()
    result = []
    for row in rows:
        record = dict(row)
        record["tenants"] = json.loads(record.pop("tenants_json"))
        result.append(record)
    return result


def _sqlite_record_application(db_path: str, row: dict[str, Any]) -> None:
    columns = ", ".join(row)
    placeholders = ", ".join(f":{key}" for key in row)
    with _connect(db_path) as connection:
        connection.execute(
            f"INSERT INTO applications ({columns}) VALUES ({placeholders})", row
        )


def _sqlite_list_applications(db_path: str) -> list[dict[str, Any]]:
    with _connect(db_path) as connection:
        rows = connection.execute(
            "SELECT * FROM applications ORDER BY created_at DESC"
        ).fetchall()
    result = []
    for row in rows:
        record = dict(row)
        record["consent_to_text"] = bool(record["consent_to_text"])
        record["roommates"] = json.loads(record.pop("roommates_json"))
        result.append(record)
    return result


def _sqlite_record_notice(db_path: str, row: dict[str, Any]) -> None:
    columns = ", ".join(row)
    placeholders = ", ".join(f":{key}" for key in row)
    with _connect(db_path) as connection:
        connection.execute(
            f"INSERT INTO notices ({columns}) VALUES ({placeholders})", row
        )


def _sqlite_list_notices(db_path: str, tenant_username: str) -> list[dict[str, Any]]:
    with _connect(db_path) as connection:
        rows = connection.execute(
            "SELECT * FROM notices WHERE tenant_username = ? "
            "ORDER BY created_at DESC",
            (tenant_username,),
        ).fetchall()
    return [dict(row) for row in rows]


def _sqlite_record_news(db_path: str, row: dict[str, Any]) -> None:
    columns = ", ".join(row)
    placeholders = ", ".join(f":{key}" for key in row)
    with _connect(db_path) as connection:
        connection.execute(
            f"INSERT INTO news ({columns}) VALUES ({placeholders})", row
        )


def _sqlite_list_news(db_path: str, landlord_id: str | None) -> list[dict[str, Any]]:
    with _connect(db_path) as connection:
        if landlord_id is None:
            rows = connection.execute(
                "SELECT * FROM news ORDER BY created_at DESC"
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM news WHERE landlord_id = ? ORDER BY created_at DESC",
                (landlord_id,),
            ).fetchall()
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Postgres backend (Supabase in practice) - one pool per DSN, created lazily
# ---------------------------------------------------------------------------

_pools: dict[str, Any] = {}
_pool_lock = asyncio.Lock()


async def _pg_pool(dsn: str):
    """A cached connection pool for `dsn`, created on first use.

    Cached by DSN rather than created once globally so tests can point
    different Settings at different databases without state leaking
    between them; in production there is only ever one DSN.
    """
    if dsn in _pools:
        return _pools[dsn]
    async with _pool_lock:
        if dsn not in _pools:
            import asyncpg

            # statement_cache_size=0: Supabase's connection pooler (the one
            # that supports IPv4 - see README's Deploying section) runs in
            # transaction mode, which does not support asyncpg's server-side
            # prepared statement cache. Without this, queries intermittently
            # fail with DuplicatePreparedStatementError.
            pool = await asyncpg.create_pool(
                dsn, min_size=1, max_size=5, statement_cache_size=0
            )
            async with pool.acquire() as connection:
                await connection.execute(POSTGRES_SCHEMA)
            _pools[dsn] = pool
    return _pools[dsn]


async def close_pools() -> None:
    """Close every cached Postgres pool. Call this from the app's shutdown."""
    for pool in _pools.values():
        await pool.close()
    _pools.clear()


async def _pg_insert(dsn: str, row: dict[str, Any]) -> None:
    pool = await _pg_pool(dsn)
    columns = ", ".join(COLUMNS)
    placeholders = ", ".join(f"${i + 1}" for i in range(len(COLUMNS)))
    values = [row.get(column) for column in COLUMNS]
    async with pool.acquire() as connection:
        await connection.execute(
            f"INSERT INTO leases ({columns}) VALUES ({placeholders})", *values
        )


async def _pg_update_status(dsn: str, document_id: str, status: str) -> bool:
    pool = await _pg_pool(dsn)
    async with pool.acquire() as connection:
        result = await connection.execute(
            "UPDATE leases SET status = $1, updated_at = $2 WHERE document_id = $3",
            status, _now(), document_id,
        )
    return result != "UPDATE 0"


async def _pg_get(dsn: str, document_id: str) -> dict[str, Any] | None:
    pool = await _pg_pool(dsn)
    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            "SELECT * FROM leases WHERE document_id = $1", document_id
        )
    if row is None:
        return None
    record = dict(row)
    record["tenants"] = json.loads(record.pop("tenants_json"))
    return record


async def _pg_record_archive(dsn: str, document_id: str, archive_file: str) -> bool:
    pool = await _pg_pool(dsn)
    now = _now()
    async with pool.acquire() as connection:
        result = await connection.execute(
            "UPDATE leases SET archive_file = $1, completed_at = $2, "
            "updated_at = $3 WHERE document_id = $4",
            archive_file, now, now, document_id,
        )
    return result != "UPDATE 0"


async def _pg_list(dsn: str, limit: int,
                   landlord_id: str | None) -> list[dict[str, Any]]:
    pool = await _pg_pool(dsn)
    async with pool.acquire() as connection:
        if landlord_id is None:
            rows = await connection.fetch(
                "SELECT * FROM leases ORDER BY created_at DESC LIMIT $1", limit
            )
        else:
            rows = await connection.fetch(
                "SELECT * FROM leases WHERE landlord_id = $1 "
                "ORDER BY created_at DESC LIMIT $2",
                landlord_id, limit,
            )
    result = []
    for row in rows:
        record = dict(row)
        record["tenants"] = json.loads(record.pop("tenants_json"))
        result.append(record)
    return result


async def _pg_record_application(dsn: str, row: dict[str, Any]) -> None:
    pool = await _pg_pool(dsn)
    columns = ", ".join(APPLICATION_COLUMNS)
    placeholders = ", ".join(f"${i + 1}" for i in range(len(APPLICATION_COLUMNS)))
    values = [row.get(column) for column in APPLICATION_COLUMNS]
    async with pool.acquire() as connection:
        await connection.execute(
            f"INSERT INTO applications ({columns}) VALUES ({placeholders})", *values
        )


async def _pg_list_applications(dsn: str) -> list[dict[str, Any]]:
    pool = await _pg_pool(dsn)
    async with pool.acquire() as connection:
        rows = await connection.fetch(
            "SELECT * FROM applications ORDER BY created_at DESC"
        )
    result = []
    for row in rows:
        record = dict(row)
        record["consent_to_text"] = bool(record["consent_to_text"])
        record["roommates"] = json.loads(record.pop("roommates_json"))
        result.append(record)
    return result


async def _pg_record_notice(dsn: str, row: dict[str, Any]) -> None:
    pool = await _pg_pool(dsn)
    columns = ", ".join(NOTICE_COLUMNS)
    placeholders = ", ".join(f"${i + 1}" for i in range(len(NOTICE_COLUMNS)))
    values = [row.get(column) for column in NOTICE_COLUMNS]
    async with pool.acquire() as connection:
        await connection.execute(
            f"INSERT INTO notices ({columns}) VALUES ({placeholders})", *values
        )


async def _pg_list_notices(dsn: str, tenant_username: str) -> list[dict[str, Any]]:
    pool = await _pg_pool(dsn)
    async with pool.acquire() as connection:
        rows = await connection.fetch(
            "SELECT * FROM notices WHERE tenant_username = $1 "
            "ORDER BY created_at DESC",
            tenant_username,
        )
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Public API - dispatches to whichever backend `db_path` names
# ---------------------------------------------------------------------------

async def init(db_path: str) -> None:
    if _is_postgres(db_path):
        await _pg_pool(db_path)  # creating the pool also runs the schema
    else:
        await asyncio.to_thread(_sqlite_init, db_path)


async def record_lease(db_path: str, *, document_id: str, document_name: str,
                       landlord_id: str, lessor_name: str,
                       premises_address: str,
                       tenants: list[dict[str, str]], tenant_email: str,
                       signing_url: str | None, signing_url_kind: str | None,
                       status: str, monthly_rent: str, term_start: str,
                       term_end: str, mode: str, created_by: str) -> None:
    timestamp = _now()
    row = {
        "document_id": document_id,
        "document_name": document_name,
        "landlord_id": landlord_id,
        "lessor_name": lessor_name,
        "premises_address": premises_address,
        "tenants_json": json.dumps(tenants),
        "tenant_email": tenant_email,
        "signing_url": signing_url,
        "signing_url_kind": signing_url_kind,
        "status": status,
        "monthly_rent": monthly_rent,
        "term_start": term_start,
        "term_end": term_end,
        "mode": mode,
        "created_by": created_by,
        "archive_file": None,
        "completed_at": None,
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    if _is_postgres(db_path):
        await _pg_insert(db_path, row)
    else:
        await asyncio.to_thread(_sqlite_insert, db_path, row)


async def update_status(db_path: str, document_id: str, status: str) -> bool:
    if _is_postgres(db_path):
        return await _pg_update_status(db_path, document_id, status)
    return await asyncio.to_thread(_sqlite_update_status, db_path, document_id, status)


async def list_leases(db_path: str, *, limit: int = 200,
                      landlord_id: str | None = None) -> list[dict[str, Any]]:
    """All leases, or only one landlord's when `landlord_id` is given."""
    if _is_postgres(db_path):
        return await _pg_list(db_path, limit, landlord_id)
    return await asyncio.to_thread(_sqlite_list, db_path, limit, landlord_id)


async def get_lease(db_path: str, document_id: str) -> dict[str, Any] | None:
    if _is_postgres(db_path):
        return await _pg_get(db_path, document_id)
    return await asyncio.to_thread(_sqlite_get, db_path, document_id)


async def record_archive(db_path: str, document_id: str,
                         archive_file: str) -> bool:
    """Note that the executed PDF has been saved to the archive."""
    if _is_postgres(db_path):
        return await _pg_record_archive(db_path, document_id, archive_file)
    return await asyncio.to_thread(
        _sqlite_record_archive, db_path, document_id, archive_file
    )


async def record_application(db_path: str, *, applicant_name: str,
                              applicant_email: str, applicant_phone: str,
                              consent_to_text: bool,
                              property_interest: str | None,
                              desired_move_in: str | None,
                              message: str | None,
                              roommates: list[dict[str, str]]) -> str:
    """Save a public rental application. Returns its generated id."""
    application_id = secrets.token_hex(12)
    row = {
        "id": application_id,
        "property_interest": property_interest,
        "applicant_name": applicant_name,
        "applicant_email": applicant_email,
        "applicant_phone": applicant_phone,
        # Plain 0/1, not a Python bool: asyncpg binds parameters by the
        # target column's declared type, and the column is INTEGER (kept
        # the same on both backends, like every other schema piece here).
        "consent_to_text": int(consent_to_text),
        "desired_move_in": desired_move_in,
        "message": message,
        "roommates_json": json.dumps(roommates),
        "created_at": _now(),
    }
    if _is_postgres(db_path):
        await _pg_record_application(db_path, row)
    else:
        await asyncio.to_thread(_sqlite_record_application, db_path, row)
    return application_id


async def list_applications(db_path: str) -> list[dict[str, Any]]:
    """Every application - admin-only at the API layer (app/main.py), since
    property_interest is free text, not a landlord id to scope by."""
    if _is_postgres(db_path):
        return await _pg_list_applications(db_path)
    return await asyncio.to_thread(_sqlite_list_applications, db_path)


async def record_notice(db_path: str, *, tenant_username: str, message: str,
                        created_by: str) -> str:
    """Save a notice for a tenant. Returns its generated id."""
    notice_id = secrets.token_hex(12)
    row = {
        "id": notice_id,
        "tenant_username": tenant_username,
        "message": message,
        "created_by": created_by,
        "created_at": _now(),
    }
    if _is_postgres(db_path):
        await _pg_record_notice(db_path, row)
    else:
        await asyncio.to_thread(_sqlite_record_notice, db_path, row)
    return notice_id


async def list_notices(db_path: str, *, tenant_username: str) -> list[dict[str, Any]]:
    """A tenant's own notices, newest first."""
    if _is_postgres(db_path):
        return await _pg_list_notices(db_path, tenant_username)
    return await asyncio.to_thread(_sqlite_list_notices, db_path, tenant_username)
