"""The properties and residents tables, and the migration off their old shape.

These run against real SQLite (a temp file), not a mock - the point is the
schema and the foreign key actually behaving, which a fake connection cannot
tell you.
"""
from __future__ import annotations

import sqlite3

import pytest

from app import db

pytestmark = pytest.mark.anyio

OLD_SCHEMA = """
CREATE TABLE properties (address TEXT PRIMARY KEY, landlord TEXT NOT NULL);
CREATE TABLE tenants (
    full_name TEXT NOT NULL, address TEXT NOT NULL, apt TEXT,
    city TEXT NOT NULL DEFAULT 'New Orleans',
    state TEXT NOT NULL DEFAULT 'LA'
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


async def test_init_creates_properties_and_residents(db_path) -> None:
    await db.init(db_path)

    assert columns(db_path, "properties") == [
        "id", "landlord_id", "address", "apt", "city", "state", "created_at",
    ]
    assert columns(db_path, "residents") == [
        "id", "property_id", "full_name", "email", "phone", "created_at",
    ]


async def test_a_resident_links_to_its_property(db_path) -> None:
    await db.init(db_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "INSERT INTO properties (id, landlord_id, address, apt, created_at) "
            "VALUES ('p1', 'lgd', '1556 Camp Street', 'B', '2026-09-07')"
        )
        connection.execute(
            "INSERT INTO residents (id, property_id, full_name, created_at) "
            "VALUES ('r1', 'p1', 'Jane Doe', '2026-09-07')"
        )
        row = connection.execute(
            "SELECT r.full_name, p.address, p.apt, p.city, p.state "
            "FROM residents r JOIN properties p ON p.id = r.property_id"
        ).fetchone()
    finally:
        connection.close()

    # city/state default to the only place this landlord operates.
    assert row == ("Jane Doe", "1556 Camp Street", "B", "New Orleans", "LA")


async def test_a_resident_cannot_point_at_a_missing_property(db_path) -> None:
    """The link is a real foreign key, not just a column that happens to
    hold an id - SQLite enforces it because _connect turns foreign keys on."""
    await db.init(db_path)
    connection = sqlite3.connect(db_path)
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO residents (id, property_id, full_name, created_at) "
                "VALUES ('r1', 'no-such-property', 'Jane Doe', '2026-09-07')"
            )
    finally:
        connection.close()


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

    assert "landlord_id" in columns(db_path, "properties")
    assert "landlord" not in columns(db_path, "properties")
    assert columns(db_path, "tenants") == []  # superseded by residents


async def test_the_migration_is_idempotent(db_path) -> None:
    """It runs on every startup, so a second pass must not drop the new
    tables it just created."""
    connection = sqlite3.connect(db_path)
    connection.executescript(OLD_SCHEMA)
    connection.commit()
    connection.close()

    await db.init(db_path)
    await db.init(db_path)

    assert "landlord_id" in columns(db_path, "properties")
    assert "property_id" in columns(db_path, "residents")


async def test_the_migration_leaves_a_populated_new_table_alone(db_path) -> None:
    await db.init(db_path)
    connection = sqlite3.connect(db_path)
    connection.execute(
        "INSERT INTO properties (id, landlord_id, address, created_at) "
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
