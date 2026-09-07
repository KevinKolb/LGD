"""app/archive_storage.py: local disk always works; Supabase Storage is
exercised with a fake client, exactly like FakePandaDoc stands in for
PandaDoc, so the suite never needs a live network Supabase project."""
from __future__ import annotations

from typing import Any

import pytest

from app import archive_storage

# anyio's pytest plugin registers itself just from anyio being installed (a
# FastAPI/Starlette dependency already) - no new test dependency needed.
# Restricted to asyncio because trio, its other backend, isn't installed.
pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Local disk backend
# ---------------------------------------------------------------------------

async def test_local_save_then_read_round_trips(tmp_path) -> None:
    directory = tmp_path / "archive"
    await archive_storage.save(str(directory), "doc-1.pdf", b"%PDF fake bytes")

    result = await archive_storage.read(str(directory), "doc-1.pdf")

    assert result == b"%PDF fake bytes"


async def test_local_read_of_a_missing_file_returns_none(tmp_path) -> None:
    directory = tmp_path / "archive"

    result = await archive_storage.read(str(directory), "never-archived.pdf")

    assert result is None


async def test_local_save_creates_the_directory_if_absent(tmp_path) -> None:
    directory = tmp_path / "does" / "not" / "exist" / "yet"

    await archive_storage.save(str(directory), "doc-1.pdf", b"bytes")

    assert (directory / "doc-1.pdf").read_bytes() == b"bytes"


async def test_local_save_leaves_no_temp_file_behind(tmp_path) -> None:
    directory = tmp_path / "archive"

    await archive_storage.save(str(directory), "doc-1.pdf", b"bytes")

    assert sorted(p.name for p in directory.iterdir()) == ["doc-1.pdf"]


# ---------------------------------------------------------------------------
# Supabase Storage backend - a fake client stands in for supabase-py
# ---------------------------------------------------------------------------

class FakeBucket:
    """Stands in for storage3's AsyncBucketProxy."""

    def __init__(self) -> None:
        self.uploads: list[dict[str, Any]] = []
        self.download_error: Exception | None = None
        self.stored: bytes | None = None

    async def upload(self, path: str, data: bytes, options: dict[str, str]) -> None:
        self.uploads.append({"path": path, "data": data, "options": options})
        self.stored = data

    async def download(self, path: str) -> bytes:
        if self.download_error is not None:
            raise self.download_error
        assert self.stored is not None, "nothing uploaded to download"
        return self.stored


class FakeStorage:
    def __init__(self, bucket: FakeBucket) -> None:
        self._bucket = bucket
        self.requested_bucket_name: str | None = None

    def from_(self, bucket_name: str) -> FakeBucket:
        self.requested_bucket_name = bucket_name
        return self._bucket


class FakeSupabaseClient:
    def __init__(self, bucket: FakeBucket) -> None:
        self.storage = FakeStorage(bucket)


@pytest.fixture
def fake_bucket() -> FakeBucket:
    return FakeBucket()


@pytest.fixture(autouse=True)
def patch_supabase_client(monkeypatch, fake_bucket):
    """Every test in this file gets the same fake client back, regardless of
    the (unused, fake) url/key passed in - so tests never need real Supabase
    credentials or network access."""

    async def fake_client(url: str, key: str) -> FakeSupabaseClient:
        return FakeSupabaseClient(fake_bucket)

    monkeypatch.setattr(archive_storage, "_supabase_client", fake_client)
    archive_storage._clients.clear()
    yield


async def test_supabase_save_uploads_to_the_named_bucket(fake_bucket) -> None:
    await archive_storage.save(
        "supabase:signed-leases", "doc-1.pdf", b"%PDF bytes",
        supabase_url="https://example.supabase.co", supabase_key="service-role-key",
    )

    assert fake_bucket.uploads == [
        {
            "path": "doc-1.pdf",
            "data": b"%PDF bytes",
            "options": {"content-type": "application/pdf", "upsert": "true"},
        }
    ]


async def test_supabase_read_returns_the_uploaded_bytes(fake_bucket) -> None:
    fake_bucket.stored = b"%PDF bytes"

    result = await archive_storage.read(
        "supabase:signed-leases", "doc-1.pdf",
        supabase_url="https://example.supabase.co", supabase_key="service-role-key",
    )

    assert result == b"%PDF bytes"


async def test_supabase_read_of_a_missing_object_returns_none(fake_bucket) -> None:
    from storage3.exceptions import StorageApiError

    fake_bucket.download_error = StorageApiError("not found", "not_found", 404)

    result = await archive_storage.read(
        "supabase:signed-leases", "never-archived.pdf",
        supabase_url="https://example.supabase.co", supabase_key="service-role-key",
    )

    assert result is None


async def test_supabase_read_reraises_a_real_error(fake_bucket) -> None:
    """A 403 means something is actually wrong (bad key, wrong bucket) and
    must not be silently treated as "not archived yet"."""
    from storage3.exceptions import StorageApiError

    fake_bucket.download_error = StorageApiError("forbidden", "forbidden", 403)

    with pytest.raises(StorageApiError):
        await archive_storage.read(
            "supabase:signed-leases", "doc-1.pdf",
            supabase_url="https://example.supabase.co", supabase_key="bad-key",
        )
