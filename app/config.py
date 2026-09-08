"""Configuration: storage paths from the environment, people from a file
or from Postgres.

Landlords and user logins live in `accounts.json` by default - gitignored,
same as `.env` - or in a Postgres `landlords`/`users` table when
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
VALID_ROLES = {ROLE_ADMIN, ROLE_MANAGER, ROLE_RESIDENT}
# Roles tied to one specific landlord, as opposed to the admin role, which
# is not. Both need a landlord_id and are checked the same way when loading
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
class Landlord:
    """A Lessor a lease can be issued under.

    `company` fills the Lessor blank on the lease. `signer_name` and `email`
    are the human who signs it - the paper lease's signature line reads
    "Lessor/Agent", so the company is the Lessor and the person is the agent.
    """

    id: str
    company: str
    signer_name: str
    email: str
@dataclass(frozen=True)
class User:
    """Someone who can log in to the dashboard."""

    username: str
    display_name: str
    role: str
    password_hash: str
    # None for admins, who are not tied to one landlord.
    landlord_id: str | None = None
    # This person's own email, separate from a landlord's - optional, since
    # existing accounts predate this field.
    email: str | None = None

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    @property
    def is_resident(self) -> bool:
        return self.role == ROLE_RESIDENT

    def may_use_landlord(self, landlord_id: str) -> bool:
        """Admins may act for any landlord; everyone else only for their own."""
        return self.is_admin or self.landlord_id == landlord_id


def _load_accounts(path: Path) -> tuple[tuple[Landlord, ...], tuple[User, ...]]:
    if not path.is_file():
        raise ConfigError(
            f"{path} does not exist. Create it with: python -m app.accounts init"
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path} is not valid JSON: {exc}") from exc

    landlords = tuple(
        Landlord(
            id=str(entry["id"]),
            company=str(entry["company"]),
            signer_name=str(entry["signer_name"]),
            email=str(entry["email"]),
        )
        for entry in raw.get("landlords", [])
    )
    if not landlords:
        raise ConfigError(f"{path} lists no landlords.")

    known_ids = {landlord.id for landlord in landlords}
    users: list[User] = []
    for entry in raw.get("users", []):
        username = str(entry["username"])
        role = normalize_role(str(entry.get("role", ROLE_MANAGER)))
        if role not in VALID_ROLES:
            raise ConfigError(
                f"User {username!r} has role {role!r}; expected one of "
                f"{sorted(VALID_ROLES)}."
            )
        landlord_id = entry.get("landlord_id")
        landlord_id = str(landlord_id) if landlord_id else None

        if role in MANAGER_SCOPED_ROLES:
            if not landlord_id:
                raise ConfigError(f"User {username!r} needs a landlord_id.")
            if landlord_id not in known_ids:
                raise ConfigError(
                    f"User {username!r} points at unknown landlord {landlord_id!r}."
                )

        password_hash = str(entry.get("password_hash", ""))
        if not password_hash:
            raise ConfigError(
                f"User {username!r} has no password yet. Set one with: "
                f"python -m app.accounts set-password {username}"
            )
        email = entry.get("email")
        users.append(
            User(
                username=username,
                display_name=str(entry.get("display_name", username)),
                role=role,
                password_hash=password_hash,
                landlord_id=landlord_id,
                email=str(email) if email else None,
            )
        )

    if not users:
        raise ConfigError(f"{path} lists no users, so nobody could log in.")

    duplicates = {u.username for u in users if
                  sum(1 for other in users if other.username == u.username) > 1}
    if duplicates:
        raise ConfigError(f"{path} has duplicate usernames: {sorted(duplicates)}")

    return landlords, tuple(users)


# Populated once, by `preload_accounts_from_postgres`, during the app's async
# startup - before anything calls `get_settings()`. `Settings.load()` stays
# synchronous (see its docstring below) so every existing caller - tests,
# other modules - keeps working unchanged; this is the only place accounts
# ever get queried over the network. When left as `None`, `Settings.load()`
# falls back to the local JSON file exactly as it always did.
_accounts_cache: tuple[tuple["Landlord", ...], tuple["User", ...]] | None = None


def _validate_accounts(
    landlords: tuple["Landlord", ...], users: list["User"], *, source: str
) -> tuple[tuple["Landlord", ...], tuple["User", ...]]:
    """The same checks `_load_accounts` applies to the JSON file, applied
    again here so a Postgres-backed accounts table can't skip them."""
    if not landlords:
        raise ConfigError(f"{source} lists no landlords.")
    known_ids = {landlord.id for landlord in landlords}
    for user in users:
        if user.role not in VALID_ROLES:
            raise ConfigError(
                f"User {user.username!r} has role {user.role!r}; expected "
                f"one of {sorted(VALID_ROLES)}."
            )
        if user.role in MANAGER_SCOPED_ROLES:
            if not user.landlord_id:
                raise ConfigError(f"User {user.username!r} needs a landlord_id.")
            if user.landlord_id not in known_ids:
                raise ConfigError(
                    f"User {user.username!r} points at unknown landlord "
                    f"{user.landlord_id!r}."
                )
        if not user.password_hash:
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
    return landlords, tuple(users)


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
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT"
        )
        # Roles were renamed landlord -> manager and tenant -> resident.
        # Idempotent, and only a tidy-up: normalize_role already maps the
        # old strings on the way in, so a login works either way.
        for old_role, new_role in LEGACY_ROLES.items():
            await connection.execute(
                "UPDATE users SET role = $1 WHERE role = $2", new_role, old_role
            )
        landlord_rows = await connection.fetch(
            "SELECT id, company, signer_name, email FROM landlords"
        )
        user_rows = await connection.fetch(
            "SELECT username, display_name, role, landlord_id, password_hash, "
            "email FROM users"
        )
    finally:
        await connection.close()

    landlords = tuple(
        Landlord(
            id=row["id"], company=row["company"],
            signer_name=row["signer_name"], email=row["email"],
        )
        for row in landlord_rows
    )
    users = [
        User(
            username=row["username"],
            display_name=row["display_name"] or row["username"],
            role=normalize_role(row["role"]),
            password_hash=row["password_hash"] or "",
            landlord_id=row["landlord_id"],
            email=row["email"],
        )
        for row in user_rows
    ]
    _accounts_cache = _validate_accounts(
        landlords, users, source="The Postgres accounts tables"
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
    landlords: tuple[Landlord, ...]
    users: tuple[User, ...]

    def landlord_by_id(self, landlord_id: str) -> Landlord | None:
        for landlord in self.landlords:
            if landlord.id == landlord_id:
                return landlord
        return None

    def user_by_username(self, username: str) -> User | None:
        for user in self.users:
            if user.username == username:
                return user
        return None

    def landlords_for(self, user: User) -> tuple[Landlord, ...]:
        """Which Lessors this user may issue a lease under."""
        if user.is_admin:
            return self.landlords
        return tuple(
            landlord for landlord in self.landlords
            if landlord.id == user.landlord_id
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
            landlords, users = _accounts_cache
        else:
            accounts_path = Path(
                os.environ.get("LGD_ACCOUNTS_FILE", str(REPO_ROOT / "accounts.json"))
            )
            landlords, users = _load_accounts(accounts_path)
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
            landlords=landlords,
            users=users,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.load()
