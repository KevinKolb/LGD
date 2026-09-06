"""SQLite persistence for generated leases.

One row per PandaDoc document. The dashboard reads this; the webhook writes
status changes to it.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

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
    -- 'sandbox' or 'production'. A sandbox lease is not legally binding, so
    -- it must stay distinguishable from a real one forever.
    mode              TEXT NOT NULL,
    created_by        TEXT NOT NULL,
    -- Filename of the archived executed PDF, once it has been fetched.
    archive_file      TEXT,
    completed_at      TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS leases_created_at ON leases (created_at DESC);
CREATE INDEX IF NOT EXISTS leases_landlord ON leases (landlord_id, created_at DESC);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect(db_path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path, timeout=10.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def _init_sync(db_path: str) -> None:
    with _connect(db_path) as connection:
        connection.executescript(SCHEMA)


def _insert_sync(db_path: str, row: dict[str, Any]) -> None:
    columns = ", ".join(row)
    placeholders = ", ".join(f":{key}" for key in row)
    with _connect(db_path) as connection:
        connection.execute(
            f"INSERT INTO leases ({columns}) VALUES ({placeholders})", row
        )


def _update_status_sync(db_path: str, document_id: str, status: str) -> bool:
    with _connect(db_path) as connection:
        cursor = connection.execute(
            "UPDATE leases SET status = ?, updated_at = ? WHERE document_id = ?",
            (status, _now(), document_id),
        )
        return cursor.rowcount > 0


def _get_sync(db_path: str, document_id: str) -> dict[str, Any] | None:
    with _connect(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM leases WHERE document_id = ?", (document_id,)
        ).fetchone()
    if row is None:
        return None
    record = dict(row)
    record["tenants"] = json.loads(record.pop("tenants_json"))
    return record


def _record_archive_sync(db_path: str, document_id: str, archive_file: str) -> bool:
    with _connect(db_path) as connection:
        cursor = connection.execute(
            "UPDATE leases SET archive_file = ?, completed_at = ?, updated_at = ? "
            "WHERE document_id = ?",
            (archive_file, _now(), _now(), document_id),
        )
        return cursor.rowcount > 0


def _list_sync(db_path: str, limit: int,
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


async def init(db_path: str) -> None:
    await asyncio.to_thread(_init_sync, db_path)


async def record_lease(db_path: str, *, document_id: str, document_name: str,
                       landlord_id: str, lessor_name: str,
                       premises_address: str,
                       tenants: list[dict[str, str]], tenant_email: str,
                       signing_url: str | None, signing_url_kind: str | None,
                       status: str, monthly_rent: str, term_start: str,
                       term_end: str, mode: str, created_by: str) -> None:
    timestamp = _now()
    await asyncio.to_thread(
        _insert_sync,
        db_path,
        {
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
            "created_at": timestamp,
            "updated_at": timestamp,
        },
    )


async def update_status(db_path: str, document_id: str, status: str) -> bool:
    return await asyncio.to_thread(_update_status_sync, db_path, document_id, status)


async def list_leases(db_path: str, *, limit: int = 200,
                      landlord_id: str | None = None) -> list[dict[str, Any]]:
    """All leases, or only one landlord's when `landlord_id` is given."""
    return await asyncio.to_thread(_list_sync, db_path, limit, landlord_id)


async def get_lease(db_path: str, document_id: str) -> dict[str, Any] | None:
    return await asyncio.to_thread(_get_sync, db_path, document_id)


async def record_archive(db_path: str, document_id: str,
                         archive_file: str) -> bool:
    """Note that the executed PDF has been saved to the archive."""
    return await asyncio.to_thread(
        _record_archive_sync, db_path, document_id, archive_file
    )
