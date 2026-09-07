"""Shared fixtures: a stubbed environment, accounts file, and fake PandaDoc."""
from __future__ import annotations

import json
from typing import Any

import pytest

# Importing app.config here, at module level - not inside a fixture -
# guarantees its load_dotenv() call (which populates os.environ from a
# developer's real .env, including DATABASE_URL/SUPABASE_*) has already run
# by the time any fixture executes, for every test session regardless of
# which specific tests are selected. Getting this wrong once meant that
# running a single test in isolation (rather than the whole suite, where
# some earlier test always imports app.config first) let the real
# DATABASE_URL slip past the delenv below - app.config wasn't imported yet
# when the delenv ran, so there was nothing yet to delete; import order
# among fixtures during test *collection* is not something to rely on for
# this, only this kind of module-level, load-first-thing import is.
import app.config  # noqa: F401
from app.auth import hash_password

SHARED_KEY = "test-shared-key"
TEMPLATE_UUID = "template-uuid-1234"

# Real Render/Supabase credentials in a developer's local .env must never
# leak into a test run - app/config.py's load_dotenv() would otherwise put
# them in os.environ, and every test that doesn't explicitly set its own
# fake DATABASE_URL (the *_postgres.py suites do) would silently start
# talking to a live Postgres/Supabase project instead of local SQLite/JSON.
# Tests stay fast, free, and offline only if this always wins.
_LIVE_CREDENTIAL_VARS = ["DATABASE_URL", "SUPABASE_URL", "SUPABASE_KEY"]


@pytest.fixture(autouse=True)
def _no_live_credentials(monkeypatch):
    for name in _LIVE_CREDENTIAL_VARS:
        monkeypatch.delenv(name, raising=False)

# Passwords are per-user so a test can prove one user cannot use another's data.
PASSWORDS = {
    "kevin": "admin password long enough",
    "steve": "steve password long enough",
    "gay": "gay password long enough",
    "tenant1": "tenant one password long",
}
ADMIN = ("kevin", PASSWORDS["kevin"])
STEVE = ("steve", PASSWORDS["steve"])
GAY = ("gay", PASSWORDS["gay"])
TENANT1 = ("tenant1", PASSWORDS["tenant1"])  # belongs to LANDLORD_LGD (steve)

LANDLORD_LGD = {
    "id": "lgd",
    "company": "LGD Properties",
    "signer_name": "Pat Landlord",
    "email": "steve-landlord@example.com",
}
LANDLORD_ROBERTSON = {
    "id": "robertson",
    "company": "Jamie Reyes Properties",
    "signer_name": "Jamie Reyes",
    "email": "gay-landlord@example.com",
}


def accounts_document() -> dict[str, Any]:
    return {
        "landlords": [LANDLORD_LGD, LANDLORD_ROBERTSON],
        "users": [
            {
                "username": "kevin",
                "display_name": "Kevin Kolb",
                "role": "admin",
                "password_hash": hash_password(PASSWORDS["kevin"], iterations=1_000),
            },
            {
                "username": "steve",
                "display_name": "Pat Landlord",
                "role": "landlord",
                "landlord_id": "lgd",
                "password_hash": hash_password(PASSWORDS["steve"], iterations=1_000),
            },
            {
                "username": "gay",
                "display_name": "Jamie Reyes",
                "role": "landlord",
                "landlord_id": "robertson",
                "password_hash": hash_password(PASSWORDS["gay"], iterations=1_000),
            },
            {
                "username": "tenant1",
                "display_name": "Tenant One",
                "role": "tenant",
                "landlord_id": "lgd",
                "password_hash": hash_password(PASSWORDS["tenant1"], iterations=1_000),
            },
        ],
    }


class FakePandaDoc:
    """Stands in for PandaDocClient, recording what the app sent."""

    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        self.created: list[dict[str, Any]] = []
        self.sent: list[dict[str, Any]] = []
        self.downloads: list[dict[str, Any]] = []
        self.shared_link: str | None = "https://app.pandadoc.com/document/fake-link"
        self.next_document_id = "doc-1"
        # None models PandaDoc still preparing the signed PDF (HTTP 202).
        self.pdf_bytes: bytes | None = b"%PDF-1.4 fake signed lease"

    async def create_document_from_template(self, **kwargs: Any) -> str:
        self.created.append(kwargs)
        return self.next_document_id

    async def wait_until_draft(self, document_id: str, **_kwargs: Any) -> None:
        return None

    async def send_document(self, document_id: str, **kwargs: Any) -> dict[str, Any]:
        self.sent.append({"document_id": document_id, **kwargs})
        return {"id": document_id, "status": "document.sent"}

    async def shared_link_for(self, document_id: str, email: str) -> str | None:
        return self.shared_link

    async def create_session_link(self, document_id: str, email: str,
                                  *, lifetime: int) -> str:
        return f"https://app.pandadoc.com/s/session-for-{email}"

    async def download_completed_pdf(self, document_id: str,
                                     *, protected: bool) -> bytes | None:
        self.downloads.append({"document_id": document_id, "protected": protected})
        return self.pdf_bytes

    async def aclose(self) -> None:
        return None


@pytest.fixture
def fake_pandadoc() -> FakePandaDoc:
    return FakePandaDoc()


@pytest.fixture
def archive_dir(tmp_path):
    return tmp_path / "archive"


@pytest.fixture
def make_client(tmp_path, monkeypatch, fake_pandadoc, archive_dir):
    """Builds a TestClient, letting a test choose the PandaDoc mode."""

    def build(mode: str = "production"):
        # Explicit, not just relying on the _no_live_credentials autouse
        # fixture's ordering relative to this one: a developer's real
        # DATABASE_URL/SUPABASE_* must be gone *before* the TestClient
        # below is constructed and entered, since entering it runs the
        # real app lifespan, which reads these vars immediately. Fixture
        # setup order between two function-scoped fixtures isn't something
        # to rely on for that - this found a real bug once already (real
        # Postgres data ended up cached in-process during a test run).
        for name in _LIVE_CREDENTIAL_VARS:
            monkeypatch.delenv(name, raising=False)
        from app.config import _reset_accounts_cache_for_tests

        _reset_accounts_cache_for_tests()

        accounts_path = tmp_path / "accounts.json"
        accounts_path.write_text(json.dumps(accounts_document()), encoding="utf-8")

        monkeypatch.setenv("PANDADOC_MODE", mode)
        monkeypatch.setenv("PANDADOC_API_KEY", "production-key")
        monkeypatch.setenv("PANDADOC_SANDBOX_API_KEY", "sandbox-key")
        monkeypatch.setenv("PANDADOC_TEMPLATE_UUID", TEMPLATE_UUID)
        monkeypatch.setenv("PANDADOC_WEBHOOK_SHARED_KEY", SHARED_KEY)
        monkeypatch.setenv("PANDADOC_SENDS_EMAIL", "false")
        monkeypatch.setenv("LGD_ACCOUNTS_FILE", str(accounts_path))
        monkeypatch.setenv("LGD_DB_PATH", str(tmp_path / "test-leases.db"))
        monkeypatch.setenv("LGD_ARCHIVE_DIR", str(archive_dir))
        monkeypatch.setenv("LGD_EARLY_PAYMENT_DISCOUNT", "50")

        from fastapi.testclient import TestClient

        from app import main
        from app.config import get_settings

        get_settings.cache_clear()
        monkeypatch.setattr(main, "PandaDocClient", lambda *a, **k: fake_pandadoc)
        return TestClient(main.app)

    yield build

    from app.config import _reset_mode_override_for_tests, get_settings

    get_settings.cache_clear()
    _reset_mode_override_for_tests()


@pytest.fixture
def client(make_client):
    """Production mode, signed in as the admin."""
    with make_client() as test_client:
        test_client.auth = ADMIN
        yield test_client
