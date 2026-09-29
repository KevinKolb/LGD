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
import re
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
--
-- A person holds any mix of four roles, as yes/no columns (the user,
-- 2026-09-29: "User can be applicant and resident ... Can be manager and
-- admin too. All one table."). On the Postgres backend their login lives on
-- this same row too - username, password_hash, auth_id - added by
-- supabase/migrations/001 (locally, logins are in accounts.json).
CREATE TABLE IF NOT EXISTS people (
    id           TEXT PRIMARY KEY,
    full_name    TEXT NOT NULL,
    first_name   TEXT,
    last_name    TEXT,
    email        TEXT,
    phone        TEXT,
    property_id  TEXT REFERENCES properties(id),
    manager_id  TEXT,
    created_at   TEXT NOT NULL,
    is_applicant BOOLEAN NOT NULL DEFAULT FALSE,
    is_resident  BOOLEAN NOT NULL DEFAULT FALSE,
    is_manager   BOOLEAN NOT NULL DEFAULT FALSE,
    is_admin     BOOLEAN NOT NULL DEFAULT FALSE,
    -- An applicant taken off the manager's list, still in the directory.
    archived_at  TEXT,
    -- The apartment an applicant is applying for, as documents/properties.json
    -- writes it ("1558 Camp St.", "A"; unit empty for a single house). Not
    -- property_id, which is where a resident lives.
    apply_address TEXT,
    apply_unit   TEXT
);
CREATE INDEX IF NOT EXISTS people_property ON people (property_id);
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
    "id", "full_name", "first_name", "last_name", "email", "phone",
    "property_id", "manager_id", "created_at",
    "is_applicant", "is_resident", "is_manager", "is_admin", "archived_at",
    "apply_address", "apply_unit",
]
ROLES = ("applicant", "resident", "manager", "admin")
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
    # A manager adding an applicant gives first and last name separately
    # (2026-09-29); full_name stays, as "first last". Supabase gets these
    # from supabase/migrations/002_manager_adds_applicants.sql as well.
    ("people", "first_name", "TEXT"),
    ("people", "last_name", "TEXT"),
    # The four roles as columns, replacing the single `role` (2026-09-29) -
    # read across once and dropped by _role_columns_sql below.
    ("people", "is_applicant", "BOOLEAN NOT NULL DEFAULT FALSE"),
    ("people", "is_resident", "BOOLEAN NOT NULL DEFAULT FALSE"),
    ("people", "is_manager", "BOOLEAN NOT NULL DEFAULT FALSE"),
    ("people", "is_admin", "BOOLEAN NOT NULL DEFAULT FALSE"),
    ("people", "archived_at", "TEXT"),
    # The apartment an applicant is applying for (2026-09-29).
    ("people", "apply_address", "TEXT"),
    ("people", "apply_unit", "TEXT"),
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

# The single people.role, read into the four role columns and dropped - on
# either backend, once (only while the column is there). On Postgres,
# supabase/migrations/001 does the same and also merges `webusers` in; the
# two agree, so it does not matter which runs first. landlord and tenant
# are that column's pre-rename spellings.
ROLE_COLUMN_MIGRATION = [
    "UPDATE people SET "
    "is_applicant = (is_applicant OR role = 'applicant'), "
    "is_resident = (is_resident OR role IN ('resident', 'tenant')), "
    "is_manager = (is_manager OR role IN ('manager', 'landlord')), "
    "is_admin = (is_admin OR role = 'admin')",
    "DROP INDEX IF EXISTS people_role",
    "ALTER TABLE people DROP COLUMN role",
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
        people_columns = [row[1] for row in connection.execute("PRAGMA table_info(people)")]
        if "role" in people_columns:
            for statement in ROLE_COLUMN_MIGRATION:
                connection.execute(statement)


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
                has_role = await connection.fetchval(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = 'people' AND column_name = 'role'"
                )
                if has_role:
                    async with connection.transaction():
                        for statement in ROLE_COLUMN_MIGRATION:
                            await connection.execute(statement)
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


async def create_person(db_path: str, *, full_name: str, role: str | None = None,
                        roles: tuple[str, ...] = (),
                        email: str | None = None, phone: str | None = None,
                        property_id: str | None = None,
                        manager_id: str | None = None) -> str:
    """Add someone to the directory, holding `role` and/or `roles`. Returns
    their generated id.

    Every login is a person, but not every person has a login: an applicant
    a manager added, or a resident who has never signed in, is a person
    with none. On Supabase a website signup makes its person itself, in a
    trigger - see supabase/migrations/001_auth_people_rls.sql.
    """
    held = set(roles) | ({role} if role else set())
    held = {"manager" if r == "landlord" else "resident" if r == "tenant" else r for r in held}
    person_id = secrets.token_hex(12)
    row = {
        "id": person_id,
        "full_name": full_name,
        "email": email,
        "phone": phone,
        "property_id": property_id,
        "manager_id": manager_id,
        "created_at": _now(),
        **{f"is_{name}": name in held for name in ROLES},
    }
    if _is_postgres(db_path):
        await _pg_create_person(db_path, row)
    else:
        await asyncio.to_thread(_sqlite_create_person, db_path, row)
    return person_id


class ApplicantError(ValueError):
    """Why an applicant could not be added or changed - worded for the
    manager page."""


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def clean_applicant(first_name: str, last_name: str, email: str, mobile: str,
                    address: str = "", unit: str = "") -> dict[str, str]:
    """The same checks, and the same wording, as create_applicant in
    supabase/migrations/002_manager_adds_applicants.sql - the website calls
    that; this app's own API calls this."""
    first, last = first_name.strip(), last_name.strip()
    email, mobile = email.strip().lower(), mobile.strip()
    address, unit = address.strip(), unit.strip()
    if not (first and last and email and mobile):
        raise ApplicantError("First name, last name, email and mobile are all needed.")
    if not address:
        raise ApplicantError("Pick the apartment they are applying for.")
    if (len(first) > 100 or len(last) > 100 or len(email) > 254 or len(mobile) > 40
            or len(address) > 200 or len(unit) > 20):
        raise ApplicantError("One of those is too long.")
    if not EMAIL_PATTERN.match(email):
        raise ApplicantError("That email address does not look right.")
    digits = re.sub(r"[^0-9]", "", mobile)
    if len(digits) < 10:
        raise ApplicantError("The mobile number needs at least 10 digits.")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10:
        mobile = f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return {"first_name": first, "last_name": last, "email": email, "mobile": mobile,
            "address": address, "unit": unit}


def applicant_view(row: dict[str, Any]) -> dict[str, Any]:
    """One applicant as the manager page shows them - the same fields as
    lgd_applicant_json in migration 002."""
    return {
        "id": row["id"],
        "first_name": row.get("first_name") or row["full_name"],
        "last_name": row.get("last_name") or "",
        "email": row.get("email"),
        "mobile": row.get("phone"),
        "created_at": row["created_at"],
        "archived": row.get("archived_at") is not None,
        "is_resident": bool(row.get("is_resident")),
        "address": row.get("apply_address") or "",
        "unit": row.get("apply_unit") or "",
    }


def _sqlite_rows(db_path: str, query: str, params: tuple = ()) -> list[dict[str, Any]]:
    with _connect(db_path) as connection:
        return [dict(row) for row in connection.execute(query, params).fetchall()]


def _sqlite_write(db_path: str, query: str, params: tuple) -> None:
    with _connect(db_path) as connection:
        connection.execute(query, params)


async def _pg_rows(dsn: str, query: str, *args: Any) -> list[dict[str, Any]]:
    pool = await _pg_pool(dsn)
    async with pool.acquire() as connection:
        return [dict(row) for row in await connection.fetch(query, *args)]


async def _pg_write(dsn: str, query: str, *args: Any) -> None:
    pool = await _pg_pool(dsn)
    async with pool.acquire() as connection:
        await connection.execute(query, *args)


async def _rows(db_path: str, query: str, *args: Any) -> list[dict[str, Any]]:
    """A SELECT on either backend, written with ? placeholders."""
    if _is_postgres(db_path):
        numbered = query
        for index in range(1, len(args) + 1):
            numbered = numbered.replace("?", f"${index}", 1)
        return await _pg_rows(db_path, numbered, *args)
    return await asyncio.to_thread(_sqlite_rows, db_path, query, args)


async def _write(db_path: str, query: str, *args: Any) -> None:
    if _is_postgres(db_path):
        numbered = query
        for index in range(1, len(args) + 1):
            numbered = numbered.replace("?", f"${index}", 1)
        await _pg_write(db_path, numbered, *args)
    else:
        await asyncio.to_thread(_sqlite_write, db_path, query, args)


async def _person(db_path: str, person_id: str) -> dict[str, Any] | None:
    rows = await _rows(db_path, "SELECT * FROM people WHERE id = ?", person_id)
    return rows[0] if rows else None


async def create_applicant(db_path: str, *, first_name: str, last_name: str,
                           email: str, mobile: str, address: str = "", unit: str = "",
                           manager_id: str | None,
                           is_admin: bool = False) -> dict[str, Any]:
    """A manager adds someone who is applying: stored now, to fill in their
    application later, and adopted by their login when they sign up with
    the same email (migration 001's trigger does that part on Supabase).

    Someone already in the directory with that email - a resident applying
    for another apartment - becomes an applicant too rather than a second
    person (the user: "User can be applicant and resident"). Raises
    ApplicantError with a reason fit to show the manager."""
    clean = clean_applicant(first_name, last_name, email, mobile, address, unit)
    existing = await _rows(
        db_path, "SELECT * FROM people WHERE lower(email) = ? ORDER BY created_at LIMIT 1",
        clean["email"])
    if existing:
        person = existing[0]
        if (not is_admin and person.get("manager_id") is not None
                and person["manager_id"] != manager_id):
            raise ApplicantError("That email belongs to someone at another company.")
        if person.get("is_applicant") and person.get("archived_at") is None:
            raise ApplicantError("That person is already on the applicant list.")
        await _write(
            db_path,
            "UPDATE people SET is_applicant = ?, archived_at = NULL, "
            "first_name = COALESCE(first_name, ?), last_name = COALESCE(last_name, ?), "
            "phone = COALESCE(phone, ?), manager_id = COALESCE(manager_id, ?), "
            "apply_address = ?, apply_unit = ? WHERE id = ?",
            True, clean["first_name"], clean["last_name"], clean["mobile"], manager_id,
            clean["address"], clean["unit"], person["id"])
        return applicant_view(await _person(db_path, person["id"]))
    person_id = secrets.token_hex(12)
    row = {
        "id": person_id,
        "full_name": f"{clean['first_name']} {clean['last_name']}",
        "first_name": clean["first_name"],
        "last_name": clean["last_name"],
        "email": clean["email"],
        "phone": clean["mobile"],
        "property_id": None,
        "manager_id": manager_id,
        "created_at": _now(),
        "is_applicant": True, "is_resident": False, "is_manager": False, "is_admin": False,
        "archived_at": None,
        "apply_address": clean["address"], "apply_unit": clean["unit"],
    }
    if _is_postgres(db_path):
        await _pg_create_person(db_path, row)
    else:
        await asyncio.to_thread(_sqlite_create_person, db_path, row)
    return applicant_view(row)


async def list_applicants(db_path: str, *, manager_id: str | None,
                          archived: bool = False) -> list[dict[str, Any]]:
    """Applicants, newest first - the current ones, or the archived ones:
    one company's, or everyone's when `manager_id` is None (an admin)."""
    query = ("SELECT * FROM people WHERE is_applicant = ? AND "
             + ("archived_at IS NOT NULL" if archived else "archived_at IS NULL"))
    args: list[Any] = [True]
    if manager_id is not None:
        query += " AND manager_id = ?"
        args.append(manager_id)
    query += " ORDER BY COALESCE(archived_at, created_at) DESC LIMIT 500"
    return [applicant_view(row) for row in await _rows(db_path, query, *args)]


async def list_residents(db_path: str, *, manager_id: str | None) -> list[dict[str, Any]]:
    """Residents with the unit they live in, for the monthly rent register:
    one company's, or everyone's when `manager_id` is None (an admin). The
    same fields as list_residents in supabase/migrations/003."""
    query = ("SELECT p.id, p.full_name, p.email, p.phone, pr.address, "
             "COALESCE(pr.apt, '') AS unit FROM people p "
             "JOIN properties pr ON pr.id = p.property_id WHERE p.is_resident = ?")
    args: list[Any] = [True]
    if manager_id is not None:
        query += " AND p.manager_id = ?"
        args.append(manager_id)
    query += " ORDER BY pr.address, pr.apt, p.full_name"
    return await _rows(db_path, query, *args)


async def set_applicant_archived(db_path: str, *, person_id: str, archived: bool,
                                 manager_id: str | None) -> dict[str, Any]:
    """Archive an applicant (off the manager's list, kept in the directory)
    or bring one back. `manager_id` None is an admin, who may touch any."""
    person = await _person(db_path, person_id)
    if (person is None or not person.get("is_applicant")
            or (manager_id is not None and person.get("manager_id") != manager_id)):
        raise ApplicantError("No such applicant.")
    await _write(db_path, "UPDATE people SET archived_at = ? WHERE id = ?",
                 _now() if archived else None, person_id)
    return applicant_view(await _person(db_path, person_id))


async def find_person(db_path: str, person_id: str) -> dict[str, Any] | None:
    """One person by id, or None."""
    if _is_postgres(db_path):
        return await _pg_find_person(db_path, person_id)
    return await asyncio.to_thread(_sqlite_find_person, db_path, person_id)
