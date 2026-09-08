"""The properties and people tables, and the migration off their old shape.

These run against real SQLite (a temp file), not a mock - the point is the
schema and the foreign key actually behaving, which a fake connection cannot
tell you.
"""
from __future__ import annotations

import sqlite3

import pytest

from app import db

pytestmark = pytest.mark.anyio

# The pre-migration shapes, spelled exactly as they exist in databases
# created back then. These names are data, not identifiers: renaming them to
# match today's vocabulary would stop db.SUPERSEDED_TABLES recognising the
# very tables it exists to clean up.
OLD_SCHEMA = """
CREATE TABLE properties (address TEXT PRIMARY KEY, landlord TEXT NOT NULL);
CREATE TABLE tenants (
    full_name TEXT NOT NULL, address TEXT NOT NULL, apt TEXT,
    city TEXT NOT NULL DEFAULT 'New Orleans',
    state TEXT NOT NULL DEFAULT 'LA'
);
CREATE TABLE residents (
    id TEXT PRIMARY KEY, property_id TEXT NOT NULL,
    full_name TEXT NOT NULL, email TEXT, phone TEXT, created_at TEXT NOT NULL
);
"""


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def db_path(tmp_path) -> str:
    return str(tmp_path / "leases.db")


def columns(path: str, table: str) -> list[str]:
    connection = sqlite3.connect(path)
    try:
        return [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]
    finally:
        connection.close()


async def test_init_creates_properties_and_people(db_path) -> None:
    await db.init(db_path)

    assert columns(db_path, "properties") == [
        "id", "manager_id", "address", "apt", "city", "state", "created_at",
    ]
    assert columns(db_path, "people") == [
        "id", "role", "full_name", "email", "phone", "property_id",
        "manager_id", "created_at",
    ]


async def test_a_person_links_to_their_property(db_path) -> None:
    await db.init(db_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "INSERT INTO properties (id, manager_id, address, apt, created_at) "
            "VALUES ('p1', 'lgd', '1556 Camp Street', 'B', '2026-09-07')"
        )
        connection.execute(
            "INSERT INTO people (id, role, full_name, property_id, created_at) "
            "VALUES ('r1', 'resident', 'Jane Doe', 'p1', '2026-09-07')"
        )
        row = connection.execute(
            "SELECT r.full_name, p.address, p.apt, p.city, p.state "
            "FROM people r JOIN properties p ON p.id = r.property_id"
        ).fetchone()
    finally:
        connection.close()

    # city/state default to the only place this manager operates.
    assert row == ("Jane Doe", "1556 Camp Street", "B", "New Orleans", "LA")


async def test_a_person_cannot_point_at_a_missing_property(db_path) -> None:
    """The link is a real foreign key, not just a column that happens to
    hold an id - SQLite enforces it because _connect turns foreign keys on."""
    await db.init(db_path)
    connection = sqlite3.connect(db_path)
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO people (id, role, full_name, property_id, created_at) "
                "VALUES ('r1', 'resident', 'Jane Doe', 'no-such-property', "
                "'2026-09-07')"
            )
    finally:
        connection.close()


async def test_a_person_with_no_property_is_allowed(db_path) -> None:
    """Only a resident lives somewhere. A manager, an admin, or an
    applicant who has not been placed yet has no unit to point at."""
    await db.init(db_path)
    connection = sqlite3.connect(db_path)
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        for role in ("manager", "admin", "applicant"):
            connection.execute(
                "INSERT INTO people (id, role, full_name, created_at) "
                f"VALUES ('{role}-1', '{role}', 'No Fixed Unit', '2026-09-07')"
            )
        connection.commit()
        count = connection.execute(
            "SELECT count(*) FROM people WHERE property_id IS NULL"
        ).fetchone()[0]
    finally:
        connection.close()
    assert count == 3


async def test_init_replaces_the_old_shaped_tables(db_path) -> None:
    """CREATE TABLE IF NOT EXISTS silently leaves an existing table's old
    columns in place. That is how a missing column took the app down once
    before, so the old properties/tenants shape has to be dropped, not
    merely re-declared."""
    connection = sqlite3.connect(db_path)
    connection.executescript(OLD_SCHEMA)
    connection.commit()
    connection.close()
    assert columns(db_path, "properties") == ["address", "landlord"]

    await db.init(db_path)

    assert "manager_id" in columns(db_path, "properties")
    assert "manager" not in columns(db_path, "properties")
    assert columns(db_path, "tenants") == []     # superseded by people
    assert columns(db_path, "residents") == []   # renamed to people
    assert "role" in columns(db_path, "people")


async def test_the_migration_is_idempotent(db_path) -> None:
    """It runs on every startup, so a second pass must not drop the new
    tables it just created."""
    connection = sqlite3.connect(db_path)
    connection.executescript(OLD_SCHEMA)
    connection.commit()
    connection.close()

    await db.init(db_path)
    await db.init(db_path)

    assert "manager_id" in columns(db_path, "properties")
    assert "property_id" in columns(db_path, "people")


async def test_the_migration_leaves_a_populated_new_table_alone(db_path) -> None:
    await db.init(db_path)
    connection = sqlite3.connect(db_path)
    connection.execute(
        "INSERT INTO properties (id, manager_id, address, created_at) "
        "VALUES ('p1', 'lgd', '1556 Camp Street', '2026-09-07')"
    )
    connection.commit()
    connection.close()

    await db.init(db_path)

    connection = sqlite3.connect(db_path)
    try:
        count = connection.execute("SELECT count(*) FROM properties").fetchone()[0]
    finally:
        connection.close()
    assert count == 1
