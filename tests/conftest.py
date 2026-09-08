"""Shared fixtures: a stubbed environment and a throwaway accounts file."""
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
                "role": "manager",
                "landlord_id": "lgd",
                "password_hash": hash_password(PASSWORDS["steve"], iterations=1_000),
            },
            {
                "username": "gay",
                "display_name": "Jamie Reyes",
                "role": "manager",
                "landlord_id": "robertson",
                "password_hash": hash_password(PASSWORDS["gay"], iterations=1_000),
            },
            {
                "username": "tenant1",
                "display_name": "Tenant One",
                "role": "resident",
                "landlord_id": "lgd",
                "password_hash": hash_password(PASSWORDS["tenant1"], iterations=1_000),
            },
        ],
    }


@pytest.fixture
def archive_dir(tmp_path):
    return tmp_path / "archive"


@pytest.fixture
def make_client(tmp_path, monkeypatch, archive_dir):
    """Builds a TestClient against a throwaway accounts file and database."""

    def build():
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

        monkeypatch.setenv("LGD_ACCOUNTS_FILE", str(accounts_path))
        monkeypatch.setenv("LGD_DB_PATH", str(tmp_path / "test-records.db"))
        monkeypatch.setenv("LGD_ARCHIVE_DIR", str(archive_dir))

        from fastapi.testclient import TestClient

        from app import main
        from app.config import get_settings

        get_settings.cache_clear()
        return TestClient(main.app)

    yield build

    from app.config import get_settings

    get_settings.cache_clear()


@pytest.fixture
def client(make_client):
    """Signed in as the admin."""
    with make_client() as test_client:
        test_client.auth = ADMIN
        yield test_client
