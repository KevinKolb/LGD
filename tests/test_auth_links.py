"""Logins, and the link between a login and the person it belongs to.

Covers the three rules this feature rests on:

1. A login is authenticated by *either* this app's PBKDF2 hash or a Supabase
   Auth identity. Requiring both would lock out whichever was created first.
2. Every login has a row in `people`; a person need not have a login.
3. The manager dashboard is an allow-list of roles. Public signups create
   `applicant` logins, and the old "anyone who is not a resident" test would
   have let every one of them into the dashboard.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import pytest

from app import config, db
from app.auth import hash_password
from app.config import (
    ConfigError,
    ROLE_ADMIN,
    ROLE_APPLICANT,
    ROLE_MANAGER,
    ROLE_RESIDENT,
    User,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATION = REPO_ROOT / "supabase" / "migrations" / "001_auth_people_rls.sql"


# ---------------------------------------------------------------------------
# 1. Either credential is enough
# ---------------------------------------------------------------------------

def write_accounts(tmp_path: Path, users: list[dict]) -> Path:
    path = tmp_path / "accounts.json"
    path.write_text(
        json.dumps(
            {
                "managers": [{
                    "id": "lgd", "name": "LGD Properties",
                    "signer_name": "Pat", "email": "pat@example.com",
                }],
                "webusers": users,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_a_supabase_only_login_loads_without_a_password_hash(tmp_path) -> None:
    """What a website signup looks like on this side: Supabase holds the
    password, so there is no PBKDF2 hash here at all."""
    path = write_accounts(tmp_path, [{
        "username": "newperson@example.com",
        "display_name": "New Person",
        "role": ROLE_APPLICANT,
        "password_hash": "",
        "auth_id": "8ac1f0e2-0000-4000-8000-000000000001",
        "person_id": "person-1",
    }])
    managers, users = config._load_accounts(path)
    assert users[0].auth_id == "8ac1f0e2-0000-4000-8000-000000000001"
    assert users[0].person_id == "person-1"
    assert users[0].password_hash == ""


def test_a_login_with_neither_credential_is_rejected(tmp_path) -> None:
    path = write_accounts(tmp_path, [{
        "username": "nobody", "display_name": "Nobody",
        "role": ROLE_MANAGER, "manager_id": "lgd", "password_hash": "",
    }])
    with pytest.raises(ConfigError, match="no password"):
        config._load_accounts(path)


def test_an_empty_hash_cannot_be_used_to_sign_in(make_client) -> None:
    """A Supabase-only account must not become a passwordless HTTP Basic
    login. Sending an empty password has to fail like any other wrong one."""
    signup = {
        "username": "signup@example.com",
        "display_name": "Web Signup",
        "role": ROLE_APPLICANT,
        "password_hash": "",
        "auth_id": "8ac1f0e2-0000-4000-8000-000000000002",
    }
    with make_client([signup]) as client:
        for password in ("", "anything", "8ac1f0e2-0000-4000-8000-000000000002"):
            response = client.get("/api/config", auth=("signup@example.com", password))
            assert response.status_code == 401, password


# ---------------------------------------------------------------------------
# 2. The dashboard is an allow-list
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "role, allowed",
    [(ROLE_ADMIN, True), (ROLE_MANAGER, True), (ROLE_RESIDENT, False),
     (ROLE_APPLICANT, False)],
)
def test_only_managers_and_admins_may_use_the_dashboard(role: str, allowed: bool) -> None:
    user = User(username="u", display_name="U", role=role, password_hash="x")
    assert user.may_use_dashboard is allowed


@pytest.mark.parametrize(
    "path",
    ["/manager/", "/admin/", "/api/config", "/api/news", "/api/blank-lease",
     "/documents/print/lease_print.html"],
)
def test_an_applicant_gets_nowhere_near_the_dashboard(make_client, path: str) -> None:
    """The reason the gate is an allow-list. `applicant` did not exist when
    it was written as "not a resident", and that phrasing would have opened
    every one of these to the first stranger who signed up on the website."""
    applicant = {
        "username": "applicant1",
        "display_name": "Hopeful Renter",
        "role": ROLE_APPLICANT,
        "password_hash": hash_password("applicant password long", iterations=1_000),
    }
    with make_client([applicant]) as client:
        response = client.get(path, auth=("applicant1", "applicant password long"))
        assert response.status_code == 404


def test_an_applicant_needs_no_manager(tmp_path) -> None:
    """Managers and residents belong to a manager; someone who has only just
    signed up on the website does not belong to one yet."""
    path = write_accounts(tmp_path, [{
        "username": "applicant1", "display_name": "Hopeful",
        "role": ROLE_APPLICANT, "password_hash": "x",
    }])
    _, users = config._load_accounts(path)
    assert users[0].manager_id is None


# ---------------------------------------------------------------------------
# 3. Every login has a person
# ---------------------------------------------------------------------------

@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_create_person_round_trips(tmp_path) -> None:
    db_path = str(tmp_path / "records.db")
    await db.init(db_path)
    person_id = await db.create_person(
        db_path, role=ROLE_RESIDENT, full_name="Jane Doe",
        email="jane@example.com", phone="504-555-0100", manager_id="lgd",
    )
    person = await db.find_person(db_path, person_id)
    assert person["full_name"] == "Jane Doe"
    assert person["role"] == ROLE_RESIDENT
    assert person["manager_id"] == "lgd"
    assert person["property_id"] is None  # nobody has been placed in a unit


@pytest.mark.anyio
async def test_a_person_can_exist_with_no_login(tmp_path) -> None:
    """The "other ways to create people" half: an applicant who filled in the
    form is a person, and no login is created for them."""
    db_path = str(tmp_path / "records.db")
    await db.init(db_path)
    person_id = await db.create_person(
        db_path, role=ROLE_APPLICANT, full_name="Walk-in Applicant"
    )
    assert await db.find_person(db_path, person_id) is not None


def test_link_people_gives_every_login_a_person(tmp_path, monkeypatch) -> None:
    from app import accounts

    monkeypatch.setenv("LGD_DB_PATH", str(tmp_path / "records.db"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    path = write_accounts(tmp_path, [
        {"username": "kevin", "display_name": "Kevin Kolb", "role": ROLE_ADMIN,
         "password_hash": "x"},
        {"username": "pam", "display_name": "Pam Hartnett", "role": ROLE_MANAGER,
         "manager_id": "lgd", "password_hash": "x"},
    ])

    assert accounts.cmd_link_people(path) == 0

    linked = json.loads(path.read_text(encoding="utf-8"))["webusers"]
    assert all(user["person_id"] for user in linked)

    connection = sqlite3.connect(tmp_path / "records.db")
    try:
        rows = dict(connection.execute("SELECT full_name, role FROM people"))
    finally:
        connection.close()
    assert rows == {"Kevin Kolb": ROLE_ADMIN, "Pam Hartnett": ROLE_MANAGER}


def test_link_people_is_safe_to_run_twice(tmp_path, monkeypatch) -> None:
    """It is the backfill as well as the rule, so re-running it must not
    hand somebody a second person row."""
    from app import accounts

    monkeypatch.setenv("LGD_DB_PATH", str(tmp_path / "records.db"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    path = write_accounts(tmp_path, [
        {"username": "kevin", "display_name": "Kevin Kolb", "role": ROLE_ADMIN,
         "password_hash": "x"},
    ])
    accounts.cmd_link_people(path)
    first = json.loads(path.read_text(encoding="utf-8"))["webusers"][0]["person_id"]
    accounts.cmd_link_people(path)
    second = json.loads(path.read_text(encoding="utf-8"))["webusers"][0]["person_id"]

    assert first == second
    connection = sqlite3.connect(tmp_path / "records.db")
    try:
        assert connection.execute("SELECT count(*) FROM people").fetchone()[0] == 1
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# The migration is the security boundary - keep it honest
# ---------------------------------------------------------------------------

def test_row_level_security_covers_every_table_without_a_list() -> None:
    """The one that matters. The browser holds a publishable Supabase key,
    and a table not covered here is readable by anyone who opens the page and
    looks - which for `applications` means every applicant's name, email and
    phone number.

    The migration used to name the tables in an array, and this test compared
    that array against the schema. Enumerating `pg_class` instead makes the
    mistake impossible rather than merely detectable: a table added to
    app/db.py later is denied by default and has to be opened deliberately.
    So what is asserted now is that the loop is still the dynamic kind.
    """
    sql = MIGRATION.read_text(encoding="utf-8")
    loop = sql.split("do $rls$")[1].split("$rls$;")[0]
    assert "from pg_class c" in loop
    assert "n.nspname = 'public'" in loop
    assert "enable row level security" in loop
    assert "revoke all on public.%I from anon, authenticated" in loop
    # No hardcoded table names to fall out of date.
    assert "array[" not in loop


def test_no_browser_policy_can_change_a_role_or_a_manager() -> None:
    """`role` and `manager_id` decide what a person is allowed to see. The
    browser may read them and nothing more: an UPDATE policy on `users`, or
    a grant covering those columns on `people`, would let a signed-in
    applicant make themselves an admin."""
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "grant update (full_name, phone) on public.people" in sql
    assert "for update to authenticated" not in sql.split("public.people")[0]
    for statement in re.findall(r"create policy .*?;", sql, re.DOTALL):
        if "on public.users" in statement:
            assert "for select" in statement, statement


def test_signups_are_created_by_confirmation_not_by_signup() -> None:
    """Adopting an existing account has to mean proving you can read that
    inbox. Firing on INSERT alone would let anyone type a manager's address
    and inherit their role."""
    sql = MIGRATION.read_text(encoding="utf-8")
    trigger = sql.split("create trigger on_auth_user_confirmed")[1].split(";")[0]
    assert "update of email_confirmed_at" in trigger
    assert "when (new.email_confirmed_at is not null)" in trigger


def test_the_publishable_key_is_the_only_supabase_key_in_the_pages() -> None:
    """The `sb_secret_...` key bypasses row level security entirely. It
    lives in .env, which is gitignored, and must never reach a file a
    browser downloads."""
    for path in (REPO_ROOT / "shared").glob("*.js"):
        # Comments stripped first. These files explain the rule in prose that
        # quotes the very strings being banned - assert on the code alone, or
        # the warning trips the test that enforces it.
        block_comments = re.sub(
            r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.DOTALL
        )
        code = re.sub(r"//.*$", "", block_comments, flags=re.MULTILINE)
        assert "sb_secret_" not in code, path
        assert "service_role" not in code, path
