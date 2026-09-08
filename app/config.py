"""Configuration: storage paths from the environment, people from a file
or from Postgres.

Managers and user logins live in `accounts.json` by default - gitignored,
same as `.env` - or in a Postgres `managers`/`webusers` table when
`DATABASE_URL` is set (see
`preload_accounts_from_postgres`). Postgres exists for Render's free tier:
local files there get wiped on every restart, so a login can't live on local
disk if this is ever deployed there; a Supabase Postgres database survives
restarts the same way a laptop's local `accounts.json` always did.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

REPO_ROOT = Path(__file__).resolve().parent.parent
ROLE_ADMIN = "admin"
ROLE_MANAGER = "manager"
ROLE_RESIDENT = "resident"
# What a public Supabase Auth signup becomes: a real login that can see its
# own details and nothing else, until someone with authority changes it.
# This role has to be *accepted* here even though nothing in this app grants
# it anything - a role the loader rejects is a role that fails startup for
# every user at once, the moment one stranger signs up on the website.
ROLE_APPLICANT = "applicant"
VALID_ROLES = {ROLE_ADMIN, ROLE_MANAGER, ROLE_RESIDENT, ROLE_APPLICANT}
# The two roles the manager dashboard and its API are for. Written as an
# allow-list rather than "not a resident": with `applicant` now arriving from
# public signups, anything phrased as an exclusion silently admits every new
# role somebody adds later.
DASHBOARD_ROLES = {ROLE_ADMIN, ROLE_MANAGER}
# Roles tied to one specific manager, as opposed to the admin role, which
# is not. Both need a manager_id and are checked the same way when loading
# accounts - see _load_accounts and _validate_accounts below.
MANAGER_SCOPED_ROLES = {ROLE_MANAGER, ROLE_RESIDENT}

# These two roles used to be stored as "landlord" and "tenant". The strings
# live in accounts.json and in the live users.role column, so a database
# written before the rename still holds the old ones. Every load maps them
# forward rather than rejecting them: startup must not depend on a
# migration having already run, or a stale database locks everyone out of
# an app whose only authentication is these rows.
LEGACY_ROLES = {"landlord": ROLE_MANAGER, "tenant": ROLE_RESIDENT}


def normalize_role(role: str) -> str:
    """Accept a role by either its current or its pre-rename name."""
    return LEGACY_ROLES.get(role, role)


class ConfigError(RuntimeError):
    """Raised when configuration is missing or self-contradictory."""


@dataclass(frozen=True)
class Manager:
    """A Lessor a lease can be issued under.

    `name` fills the Lessor blank on the lease. `signer_name` and `email`
    are the human who signs it - the paper lease's signature line reads
    "Lessor/Agent", so the manager is the Lessor and the person is the agent.
    """

    id: str
    name: str
    signer_name: str
    email: str
@dataclass(frozen=True)
class User:
    """Someone who can log in.

    Two different things can authenticate this person, and either is enough:

    - `password_hash`, checked by this app's HTTP Basic auth (app/auth.py).
    - `auth_id`, the Supabase Auth identity that the live website's login
      page uses. Supabase holds that password; this app never sees it.

    A row created by a website signup has an `auth_id` and an empty
    `password_hash`, and one created by `python -m app.accounts` has the
    reverse. Requiring both would lock out whichever half was created first.
    """

    username: str
    display_name: str
    role: str
    password_hash: str
    # None for admins, who are not tied to one manager.
    manager_id: str | None = None
    # This person's own email, separate from a manager's - optional, since
    # existing accounts predate this field.
    email: str | None = None
    # The Supabase Auth identity (a uuid, as a string) behind this login.
    auth_id: str | None = None
    # This login's row in the `people` directory. Every user has one - see
    # supabase/migrations/001_auth_people_rls.sql, which enforces it in the
    # database itself. Optional here only because a local accounts.json
    # written before that migration will not carry it.
    person_id: str | None = None

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    @property
    def is_resident(self) -> bool:
        return self.role == ROLE_RESIDENT

    @property
    def may_use_dashboard(self) -> bool:
        """Managers and admins only - not residents, not applicants."""
        return self.role in DASHBOARD_ROLES

    def may_use_manager(self, manager_id: str) -> bool:
        """Admins may act for any manager; everyone else only for their own."""
        return self.is_admin or self.manager_id == manager_id


def _load_accounts(path: Path) -> tuple[tuple[Manager, ...], tuple[User, ...]]:
    if not path.is_file():
        raise ConfigError(
            f"{path} does not exist. Create it with: python -m app.accounts init"
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path} is not valid JSON: {exc}") from exc

    # Both key spellings are accepted on the way in. This file predates the
    # landlords -> managers rename and lives outside the repo (it is
    # gitignored, and holds real password hashes), so it cannot be migrated
    # by editing a committed file - and a login that stops working because a
    # key was renamed is the worst possible failure here.
    manager_entries = raw.get("managers") or raw.get("landlords") or []
    managers = tuple(
        Manager(
            id=str(entry["id"]),
            name=str(entry.get("name") or entry["company"]),
            signer_name=str(entry["signer_name"]),
            email=str(entry["email"]),
        )
        for entry in manager_entries
    )
    if not managers:
        raise ConfigError(f"{path} lists no managers.")

    known_ids = {manager.id for manager in managers}
    users: list[User] = []
    for entry in raw.get("webusers") or raw.get("users") or []:
        username = str(entry["username"])
        role = normalize_role(str(entry.get("role", ROLE_MANAGER)))
        if role not in VALID_ROLES:
            raise ConfigError(
                f"User {username!r} has role {role!r}; expected one of "
                f"{sorted(VALID_ROLES)}."
            )
        manager_id = entry.get("manager_id") or entry.get("landlord_id")
        manager_id = str(manager_id) if manager_id else None

        if role in MANAGER_SCOPED_ROLES:
            if not manager_id:
                raise ConfigError(f"User {username!r} needs a manager_id.")
            if manager_id not in known_ids:
                raise ConfigError(
                    f"User {username!r} points at unknown manager {manager_id!r}."
                )

        password_hash = str(entry.get("password_hash", ""))
        auth_id = entry.get("auth_id")
        if not password_hash and not auth_id:
            raise ConfigError(
                f"User {username!r} has no password yet. Set one with: "
                f"python -m app.accounts set-password {username}"
            )
        email = entry.get("email")
        person_id = entry.get("person_id")
        users.append(
            User(
                username=username,
                display_name=str(entry.get("display_name", username)),
                role=role,
                password_hash=password_hash,
                manager_id=manager_id,
                email=str(email) if email else None,
                auth_id=str(auth_id) if auth_id else None,
                person_id=str(person_id) if person_id else None,
            )
        )

    if not users:
        raise ConfigError(f"{path} lists no users, so nobody could log in.")

    duplicates = {u.username for u in users if
                  sum(1 for other in users if other.username == u.username) > 1}
    if duplicates:
        raise ConfigError(f"{path} has duplicate usernames: {sorted(duplicates)}")

    return managers, tuple(users)


# Populated once, by `preload_accounts_from_postgres`, during the app's async
# startup - before anything calls `get_settings()`. `Settings.load()` stays
# synchronous (see its docstring below) so every existing caller - tests,
# other modules - keeps working unchanged; this is the only place accounts
# ever get queried over the network. When left as `None`, `Settings.load()`
# falls back to the local JSON file exactly as it always did.
_accounts_cache: tuple[tuple["Manager", ...], tuple["User", ...]] | None = None


def _validate_accounts(
    managers: tuple["Manager", ...], users: list["User"], *, source: str
) -> tuple[tuple["Manager", ...], tuple["User", ...]]:
    """The same checks `_load_accounts` applies to the JSON file, applied
    again here so a Postgres-backed accounts table can't skip them."""
    if not managers:
        raise ConfigError(f"{source} lists no managers.")
    known_ids = {manager.id for manager in managers}
    for user in users:
        if user.role not in VALID_ROLES:
            raise ConfigError(
                f"User {user.username!r} has role {user.role!r}; expected "
                f"one of {sorted(VALID_ROLES)}."
            )
        if user.role in MANAGER_SCOPED_ROLES:
            if not user.manager_id:
                raise ConfigError(f"User {user.username!r} needs a manager_id.")
            if user.manager_id not in known_ids:
                raise ConfigError(
                    f"User {user.username!r} points at unknown manager "
                    f"{user.manager_id!r}."
                )
        if not user.password_hash and not user.auth_id:
            raise ConfigError(
                f"User {user.username!r} has no password yet. Set one with: "
                f"python -m app.accounts set-password {user.username}"
            )
    if not users:
        raise ConfigError(f"{source} lists no users, so nobody could log in.")
    duplicates = {u.username for u in users if
                  sum(1 for other in users if other.username == u.username) > 1}
    if duplicates:
        raise ConfigError(f"{source} has duplicate usernames: {sorted(duplicates)}")
    return managers, tuple(users)


async def preload_accounts_from_postgres(dsn: str) -> None:
    """Query Postgres once and cache the result for every later, synchronous
    `Settings.load()` call to read. Call this during the app's async startup
    (see `app/main.py`'s `lifespan`), before anything calls `get_settings()`.
    """
    global _accounts_cache
    import asyncpg

    # statement_cache_size=0: see the matching comment in app/db.py - required
    # for Supabase's transaction-mode connection pooler.
    connection = await asyncpg.connect(dsn, statement_cache_size=0)
    try:
        # users.email was added after the first deployment, so a live table
        # can predate it. `accounts init` (which is what creates these
        # tables) is not re-run against an existing deployment, and the
        # SELECT below hard-fails startup on a table without the column -
        # so bring it up to date here, idempotently, the same way
        # app/db.py runs CREATE TABLE IF NOT EXISTS on every pool.
        await connection.execute(
            "ALTER TABLE webusers ADD COLUMN IF NOT EXISTS email TEXT"
        )
        # Same reasoning for the two columns that link a login to Supabase
        # Auth and to its `people` row. The full version of this migration -
        # with the triggers and the row level security that go with it -
        # lives in supabase/migrations/001_auth_people_rls.sql; these two
        # lines exist so that merely *starting* the app against a database
        # that has not had it applied yet cannot fail on a missing column.
        await connection.execute(
            "ALTER TABLE webusers ADD COLUMN IF NOT EXISTS auth_id UUID"
        )
        await connection.execute(
            "ALTER TABLE webusers ADD COLUMN IF NOT EXISTS person_id TEXT"
        )
        # Roles were renamed landlord -> manager and tenant -> resident.
        # Idempotent, and only a tidy-up: normalize_role already maps the
        # old strings on the way in, so a login works either way.
        for old_role, new_role in LEGACY_ROLES.items():
            await connection.execute(
                "UPDATE webusers SET role = $1 WHERE role = $2", new_role, old_role
            )
        manager_rows = await connection.fetch(
            "SELECT id, name, signer_name, email FROM managers"
        )
        user_rows = await connection.fetch(
            "SELECT username, display_name, role, manager_id, password_hash, "
            "email, auth_id, person_id FROM webusers"
        )
    finally:
        await connection.close()

    managers = tuple(
        Manager(
            id=row["id"], name=row["name"],
            signer_name=row["signer_name"], email=row["email"],
        )
        for row in manager_rows
    )
    users = [
        User(
            username=row["username"],
            display_name=row["display_name"] or row["username"],
            role=normalize_role(row["role"]),
            password_hash=row["password_hash"] or "",
            manager_id=row["manager_id"],
            email=row["email"],
            auth_id=str(row["auth_id"]) if row["auth_id"] else None,
            person_id=row["person_id"],
        )
        for row in user_rows
    ]
    _accounts_cache = _validate_accounts(
        managers, users, source="The Postgres accounts tables"
    )


def _reset_accounts_cache_for_tests() -> None:
    """Test-only escape hatch: clear the preloaded cache so a test can go
    back to exercising the local-JSON-file path after a Postgres test."""
    global _accounts_cache
    _accounts_cache = None

@dataclass(frozen=True)
class Settings:
    db_path: str
    # A local directory, or "supabase:<bucket-name>" (see supabase_url and
    # supabase_key). Nothing writes here yet - kept for the mail-merge
    # output this app is heading toward.
    archive_dir: str
    # Only used when archive_dir names a supabase: bucket.
    supabase_url: str
    supabase_key: str
    managers: tuple[Manager, ...]
    users: tuple[User, ...]

    def manager_by_id(self, manager_id: str) -> Manager | None:
        for manager in self.managers:
            if manager.id == manager_id:
                return manager
        return None

    def user_by_username(self, username: str) -> User | None:
        for user in self.users:
            if user.username == username:
                return user
        return None

    def managers_for(self, user: User) -> tuple[Manager, ...]:
        """Which Lessors this user may issue a lease under."""
        if user.is_admin:
            return self.managers
        return tuple(
            manager for manager in self.managers
            if manager.id == user.manager_id
        )

    @classmethod
    def load(cls) -> "Settings":
        """Deliberately synchronous, so every existing caller (routes, tests,
        `get_settings()`) keeps working unchanged. If `DATABASE_URL` is set,
        accounts must already be sitting in `_accounts_cache` - populated by
        `preload_accounts_from_postgres` during the app's async startup -
        rather than queried here; this function only ever reads that cache
        or the local JSON file, never the network.
        """
        if _accounts_cache is not None:
            managers, users = _accounts_cache
        else:
            accounts_path = Path(
                os.environ.get("LGD_ACCOUNTS_FILE", str(REPO_ROOT / "accounts.json"))
            )
            managers, users = _load_accounts(accounts_path)
        # A Postgres DSN if configured (Render's free tier wipes local files
        # on restart), else the local SQLite file exactly as always.
        db_path = os.environ.get("DATABASE_URL", "").strip() or os.environ.get(
            "LGD_DB_PATH", "leases.db"
        )
        return cls(
            db_path=db_path,
            archive_dir=os.environ.get(
                "LGD_ARCHIVE_DIR", str(REPO_ROOT / "archive")
            ),
            supabase_url=os.environ.get("SUPABASE_URL", "").strip(),
            supabase_key=os.environ.get("SUPABASE_KEY", "").strip(),
            managers=managers,
            users=users,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.load()
