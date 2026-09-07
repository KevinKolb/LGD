"""Where executed lease PDFs live: a local folder, or Supabase Storage.

Chosen the same way `app/db.py` chooses SQLite vs Postgres: by what's
configured, not a hardcoded switch. `location` is either a local directory
path (e.g. "archive") or "supabase:<bucket-name>" naming a Supabase Storage
bucket - the bucket itself must already exist (create it once, manually, in
the Supabase dashboard; this module never creates one).

Exists for the same reason the Postgres backend in `app/db.py` does: Render's
free tier wipes local files on every restart, so an archived signed lease
can't live on local disk if this is ever deployed there.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

SUPABASE_PREFIX = "supabase:"


def _is_supabase(location: str) -> bool:
    return location.startswith(SUPABASE_PREFIX)


def _bucket_name(location: str) -> str:
    return location.removeprefix(SUPABASE_PREFIX)


# One client per (url, key) pair, created lazily - mirrors app/db.py's
# per-DSN connection pool caching, and for the same reason: tests can point
# different Settings at different (fake) credentials without state leaking
# between them, while production only ever has one pair.
_clients: dict[tuple[str, str], Any] = {}


async def _supabase_client(url: str, key: str):
    cache_key = (url, key)
    if cache_key not in _clients:
        from supabase import create_async_client

        _clients[cache_key] = await create_async_client(url, key)
    return _clients[cache_key]


async def save(location: str, filename: str, data: bytes, *,
               supabase_url: str = "", supabase_key: str = "") -> None:
    if _is_supabase(location):
        client = await _supabase_client(supabase_url, supabase_key)
        bucket = client.storage.from_(_bucket_name(location))
        options = {"content-type": "application/pdf", "upsert": "true"}
        # upsert=true covers both "first archive" and "re-archive after a
        # partial failure" the same way the local backend's overwrite-safe
        # write does, without needing a separate exists()-then-branch call.
        await bucket.upload(filename, data, options)
    else:
        await asyncio.to_thread(_local_save_sync, location, filename, data)


async def read(location: str, filename: str, *,
               supabase_url: str = "", supabase_key: str = "") -> bytes | None:
    if _is_supabase(location):
        return await _supabase_read(location, filename, supabase_url, supabase_key)
    return await asyncio.to_thread(_local_read_sync, location, filename)


async def _supabase_read(location: str, filename: str, supabase_url: str,
                         supabase_key: str) -> bytes | None:
    from storage3.exceptions import StorageApiError

    client = await _supabase_client(supabase_url, supabase_key)
    bucket = client.storage.from_(_bucket_name(location))
    try:
        return await bucket.download(filename)
    except StorageApiError as exc:
        # A missing object means "not archived yet" to every caller of this
        # module - the same as a missing local file. Anything else (auth
        # failure, a misconfigured bucket) is a real error and must not be
        # swallowed as if the PDF just weren't ready.
        if str(exc.status) in ("404", "400"):
            return None
        raise


def _local_save_sync(directory: str, filename: str, data: bytes) -> None:
    archive_dir = Path(directory)
    archive_dir.mkdir(parents=True, exist_ok=True)
    # Write then rename, so a crash mid-write can't leave a torn file
    # recorded as archived.
    temporary = archive_dir / f".{filename}.part"
    temporary.write_bytes(data)
    temporary.replace(archive_dir / filename)


def _local_read_sync(directory: str, filename: str) -> bytes | None:
    path = Path(directory) / filename
    if not path.is_file():
        return None
    return path.read_bytes()
