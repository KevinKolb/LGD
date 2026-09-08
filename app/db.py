"""Record persistence: SQLite locally, Postgres (e.g. Supabase) in production.

Every public function here takes `db_path` as its first argument, exactly as
before this file supported two backends. Which backend actually runs is
decided purely by what `db_path` looks like:

    "records.db"                         -> SQLite (a local file)
    "postgres://..." / "postgresql://..." -> Postgres, via asyncpg

This means `app/main.py` never needs to know which backend is active - it
just passes `settings.db_path` through unchanged. The point of the second
backend is Render's free tier: local files there get wiped on every restart,
so a record can't live on local disk if this is ever deployed there.
Postgres (a free Supabase project, in practice) survives restarts; SQLite is
what tests use, and what running this on a laptop always used.
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
-- Public rental applications, submitted from the tenant page with no login.
-- property_interest is free text, not a manager id - see ApplicationRequest
-- in app/tenant_portal.py - so these are never manager-scoped, admin-only.
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

-- One row per rentable unit. Keyed on a generated id rather than on the
-- address: one street address can hold several units, and an address that
-- gets retyped or reformatted would otherwise orphan every resident
-- pointing at it.
CREATE TABLE IF NOT EXISTS properties (
    id           TEXT PRIMARY KEY,
    manager_id  TEXT NOT NULL,
    address      TEXT NOT NULL,
    apt          TEXT,
    city         TEXT NOT NULL DEFAULT 'New Orleans',
    state        TEXT NOT NULL DEFAULT 'LA',
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS properties_manager ON properties (manager_id, address);

-- Everyone this system knows about, whatever their relationship to it:
-- residents, managers, admins and applicants all live here.
--
-- property_id is a real foreign key, so nobody can point at a property
-- that does not exist (SQLite enforces this too - see PRAGMA foreign_keys
-- in _connect). It is nullable because only a resident lives somewhere: a
-- manager, an admin, or an applicant who has not been placed yet has no
-- unit to point at.
--
-- Logging in runs off the separate `users` table (see app/accounts.py).
-- The two are linked from that side: `users.person_id` points here, and
-- every login has exactly one row in this table. Not the reverse - most
-- people never log in at all. See CLAUDE.md.
--
-- manager_id carries no REFERENCES for the same reason properties.manager_id
-- does not: the `managers` table only exists on the Postgres backend, since
-- locally that data lives in accounts.json. The real foreign key is added by
-- supabase/migrations/001_auth_people_rls.sql, where the target table exists.
CREATE TABLE IF NOT EXISTS people (
    id           TEXT PRIMARY KEY,
    role         TEXT NOT NULL,
    full_name    TEXT NOT NULL,
    email        TEXT,
    phone        TEXT,
    property_id  TEXT REFERENCES properties(id),
    manager_id  TEXT,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS people_property ON people (property_id);
CREATE INDEX IF NOT EXISTS people_role ON people (role);
CREATE INDEX IF NOT EXISTS people_manager ON people (manager_id);

-- News a manager/admin posts, from the manager dashboard. created_at is
-- recorded in Central time (see _now_central below), unlike every other
-- table here, which records UTC - a deliberate one-off per the user's
-- request, not a general policy change.
CREATE TABLE IF NOT EXISTS news (
    id           TEXT PRIMARY KEY,
    manager_id  TEXT NOT NULL,
    headline     TEXT NOT NULL,
    article      TEXT NOT NULL,
    created_by   TEXT NOT NULL,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS news_created_at ON news (created_at DESC);
CREATE INDEX IF NOT EXISTS news_manager ON news (manager_id, created_at DESC);
"""

APPLICATION_COLUMNS = [
    "id", "property_interest", "applicant_name", "applicant_email",
    "applicant_phone", "consent_to_text", "desired_move_in", "message",
    "roommates_json", "created_at",
]
PERSON_COLUMNS = [
    "id", "role", "full_name", "email", "phone", "property_id", "manager_id",
    "created_at",
]
NEWS_COLUMNS = ["id", "manager_id", "headline", "article", "created_by", "created_at"]

# The same DDL is valid on both backends. Kept as one derived constant so a
# future column change cannot update one schema and miss the other.
POSTGRES_SCHEMA = SCHEMA.replace(
    "CREATE INDEX IF NOT EXISTS", "CREATE INDEX IF NOT EXISTS"
)


def _now() -> str:
    # Microsecond precision, not just seconds: two rows created in quick
    # succession (e.g. two news posts published back to back) still need a
    # distinct, reliably orderable created_at for "ORDER BY created_at DESC"
    # to return them in the right order.
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _now_central() -> str:
    """Like _now(), but in Central time (America/Chicago) rather than UTC -
    only news posts record a timestamp this way, per the user's request.
    Still unambiguous (isoformat keeps the UTC offset, which also correctly
    shifts between CST/CDT on its own), just expressed in Central local
    time instead of UTC."""
    return datetime.now(CENTRAL_TIME).isoformat(timespec="microseconds")


# Tables an earlier version of this schema created with a different shape.
# CREATE TABLE IF NOT EXISTS does not reshape an existing table - it leaves
# the old columns sitting there and reports success, which is exactly how a
# missing column took the whole app down once already (see the users.email
# migration in app/config.py). None of these are read or written any more,
# so replacing or retiring them outright loses nothing.
#
# Each entry is (table, column unique to the OLD shape). The column is the
# guard: it only matches a table left over from the old schema, so this is
# idempotent and will not touch the new tables on any later startup.
# Columns added to a table that already existed. CREATE TABLE IF NOT EXISTS
# silently leaves an old table's shape alone, so a column added here after a
# database was first created has to be added again, explicitly, on every
# startup - the same guarded-migration pattern app/config.py uses for
# users.email, and for the same reason: skipping it is what took the live app
# down on 2026-09-07.
ADDED_COLUMNS = [
    ("people", "manager_id", "TEXT"),
    # The live applications table was created before the application form
    # grew these three, and CREATE TABLE IF NOT EXISTS will not add them.
    # Found on 2026-09-08 by comparing the deployed table against SCHEMA:
    # every one of these is written by record_application, so submitting an
    # application would have failed against production the moment the form
    # was pointed at it.
    ("applications", "property_interest", "TEXT"),
    ("applications", "consent_to_text", "INTEGER NOT NULL DEFAULT 0"),
    ("applications", "roommates_json", "TEXT NOT NULL DEFAULT '[]'"),
]

SUPERSEDED_TABLES = [
    ("properties", "landlord"),  # old shape: (address PRIMARY KEY, landlord)
    ("tenants", "full_name"),     # superseded by people
    ("residents", "full_name"),   # renamed to people, which covers every role
    ("leases", "document_id"),    # PandaDoc document tracking, feature removed
    ("notices", "tenant_username"),  # manager-to-resident messages, feature removed
]


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
        for table, old_column in SUPERSEDED_TABLES:
            # Table names come from the constant above, never from input.
            columns = [
                row[1] for row in connection.execute(f"PRAGMA table_info({table})")
            ]
            if old_column in columns:
                connection.execute(f"DROP TABLE {table}")
        connection.executescript(SCHEMA)
        for table, column, column_type in ADDED_COLUMNS:
            # Names come from the constant above, never from input. SQLite
            # has no ADD COLUMN IF NOT EXISTS, so check first.
            existing = [
                row[1] for row in connection.execute(f"PRAGMA table_info({table})")
            ]
            if column not in existing:
                connection.execute(
                    f"ALTER TABLE {table} ADD COLUMN {column} {column_type}"
                )


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


def _sqlite_create_person(db_path: str, row: dict[str, Any]) -> None:
    columns = ", ".join(row)
    placeholders = ", ".join(f":{key}" for key in row)
    with _connect(db_path) as connection:
        connection.execute(
            f"INSERT INTO people ({columns}) VALUES ({placeholders})", row
        )


def _sqlite_find_person(db_path: str, person_id: str) -> dict[str, Any] | None:
    with _connect(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM people WHERE id = ?", (person_id,)
        ).fetchone()
    return dict(row) if row else None


def _sqlite_record_news(db_path: str, row: dict[str, Any]) -> None:
    columns = ", ".join(row)
    placeholders = ", ".join(f":{key}" for key in row)
    with _connect(db_path) as connection:
        connection.execute(
            f"INSERT INTO news ({columns}) VALUES ({placeholders})", row
        )


def _sqlite_list_news(db_path: str, manager_id: str | None) -> list[dict[str, Any]]:
    with _connect(db_path) as connection:
        if manager_id is None:
            rows = connection.execute(
                "SELECT * FROM news ORDER BY created_at DESC"
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM news WHERE manager_id = ? ORDER BY created_at DESC",
                (manager_id,),
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
                for table, old_column in SUPERSEDED_TABLES:
                    stale = await connection.fetchval(
                        "SELECT 1 FROM information_schema.columns "
                        "WHERE table_name = $1 AND column_name = $2",
                        table, old_column,
                    )
                    if stale:
                        # Table name comes from the constant, never from input.
                        await connection.execute(f'DROP TABLE "{table}"')
                await connection.execute(POSTGRES_SCHEMA)
                for table, column, column_type in ADDED_COLUMNS:
                    # Names come from the constant above, never from input.
                    await connection.execute(
                        f'ALTER TABLE "{table}" '
                        f'ADD COLUMN IF NOT EXISTS "{column}" {column_type}'
                    )
            _pools[dsn] = pool
    return _pools[dsn]


async def close_pools() -> None:
    """Close every cached Postgres pool. Call this from the app's shutdown."""
    for pool in _pools.values():
        await pool.close()
    _pools.clear()


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


async def _pg_create_person(dsn: str, row: dict[str, Any]) -> None:
    pool = await _pg_pool(dsn)
    columns = ", ".join(PERSON_COLUMNS)
    placeholders = ", ".join(f"${i + 1}" for i in range(len(PERSON_COLUMNS)))
    values = [row.get(column) for column in PERSON_COLUMNS]
    async with pool.acquire() as connection:
        await connection.execute(
            f"INSERT INTO people ({columns}) VALUES ({placeholders})", *values
        )


async def _pg_find_person(dsn: str, person_id: str) -> dict[str, Any] | None:
    pool = await _pg_pool(dsn)
    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            "SELECT * FROM people WHERE id = $1", person_id
        )
    return dict(row) if row else None


async def _pg_record_news(dsn: str, row: dict[str, Any]) -> None:
    pool = await _pg_pool(dsn)
    columns = ", ".join(NEWS_COLUMNS)
    placeholders = ", ".join(f"${i + 1}" for i in range(len(NEWS_COLUMNS)))
    values = [row.get(column) for column in NEWS_COLUMNS]
    async with pool.acquire() as connection:
        await connection.execute(
            f"INSERT INTO news ({columns}) VALUES ({placeholders})", *values
        )


async def _pg_list_news(dsn: str, manager_id: str | None) -> list[dict[str, Any]]:
    pool = await _pg_pool(dsn)
    async with pool.acquire() as connection:
        if manager_id is None:
            rows = await connection.fetch("SELECT * FROM news ORDER BY created_at DESC")
        else:
            rows = await connection.fetch(
                "SELECT * FROM news WHERE manager_id = $1 ORDER BY created_at DESC",
                manager_id,
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
    property_interest is free text, not a manager id to scope by."""
    if _is_postgres(db_path):
        return await _pg_list_applications(db_path)
    return await asyncio.to_thread(_sqlite_list_applications, db_path)


async def record_news(db_path: str, *, manager_id: str, headline: str,
                      article: str, created_by: str) -> str:
    """Save a news post. Returns its generated id. created_at is Central
    time (see _now_central), not UTC like everything else in this file."""
    news_id = secrets.token_hex(12)
    row = {
        "id": news_id,
        "manager_id": manager_id,
        "headline": headline,
        "article": article,
        "created_by": created_by,
        "created_at": _now_central(),
    }
    if _is_postgres(db_path):
        await _pg_record_news(db_path, row)
    else:
        await asyncio.to_thread(_sqlite_record_news, db_path, row)
    return news_id


async def list_news(db_path: str, *,
                    manager_id: str | None = None) -> list[dict[str, Any]]:
    """All news, or only one manager's when `manager_id` is given."""
    if _is_postgres(db_path):
        return await _pg_list_news(db_path, manager_id)
    return await asyncio.to_thread(_sqlite_list_news, db_path, manager_id)


async def create_person(db_path: str, *, role: str, full_name: str,
                        email: str | None = None, phone: str | None = None,
                        property_id: str | None = None,
                        manager_id: str | None = None) -> str:
    """Add someone to the directory. Returns their generated id.

    Creating a *login* is what has to create one of these (every user has a
    person), but the reverse is not true and never will be: an applicant who
    filled in the form, or a resident who has never signed in, is a person
    with no user. This is the "other ways to create people" half.

    On the Supabase backend a login inserted directly into `users` gets its
    person row from a database trigger instead, so that the rule holds even
    for rows this code never sees - see
    supabase/migrations/001_auth_people_rls.sql.
    """
    person_id = secrets.token_hex(12)
    row = {
        "id": person_id,
        "role": role,
        "full_name": full_name,
        "email": email,
        "phone": phone,
        "property_id": property_id,
        "manager_id": manager_id,
        "created_at": _now(),
    }
    if _is_postgres(db_path):
        await _pg_create_person(db_path, row)
    else:
        await asyncio.to_thread(_sqlite_create_person, db_path, row)
    return person_id


async def find_person(db_path: str, person_id: str) -> dict[str, Any] | None:
    """One person by id, or None."""
    if _is_postgres(db_path):
        return await _pg_find_person(db_path, person_id)
    return await asyncio.to_thread(_sqlite_find_person, db_path, person_id)
