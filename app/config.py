"""Configuration: PandaDoc settings from the environment, people from a file
or from Postgres.

Secrets and API wiring live in `.env`. Landlords and user logins live in
`accounts.json` by default - gitignored, same as `.env` - or in a Postgres
`landlords`/`users` table when `DATABASE_URL` is set (see
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
ROLE_LANDLORD = "landlord"
ROLE_TENANT = "tenant"
VALID_ROLES = {ROLE_ADMIN, ROLE_LANDLORD, ROLE_TENANT}
# Roles tied to one specific landlord, as opposed to the admin role, which
# is not. Both need a landlord_id and are checked the same way when loading
# accounts - see _load_accounts and _validate_accounts below.
LANDLORD_SCOPED_ROLES = {ROLE_LANDLORD, ROLE_TENANT}

MODE_SANDBOX = "sandbox"
MODE_PRODUCTION = "production"
VALID_MODES = {MODE_SANDBOX, MODE_PRODUCTION}


class ConfigError(RuntimeError):
    """Raised when configuration is missing or self-contradictory."""


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(
            f"{name} is not set. Copy .env.example to .env and fill it in "
            f"(see pandadoc/TEMPLATE_SETUP.md)."
        )
    return value


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


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
    def is_tenant(self) -> bool:
        return self.role == ROLE_TENANT

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
        role = str(entry.get("role", ROLE_LANDLORD))
        if role not in VALID_ROLES:
            raise ConfigError(
                f"User {username!r} has role {role!r}; expected one of "
                f"{sorted(VALID_ROLES)}."
            )
        landlord_id = entry.get("landlord_id")
        landlord_id = str(landlord_id) if landlord_id else None

        if role in LANDLORD_SCOPED_ROLES:
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
        if user.role in LANDLORD_SCOPED_ROLES:
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
            role=row["role"],
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


# An admin-set runtime override, from the dashboard's sandbox/live toggle -
# takes precedence over PANDADOC_MODE when set. Deliberately in-memory only,
# not persisted anywhere: a restart forgetting a "production" override and
# falling back to the safe env-var default (sandbox, unless the deployment's
# own PANDADOC_MODE says otherwise) is a feature, not a bug.
_mode_override: str | None = None


def set_mode_override(mode: str | None) -> None:
    """Set (or, with None, clear) the runtime mode override. Raises
    ConfigError for anything other than a valid mode or None."""
    global _mode_override
    if mode is not None and mode not in VALID_MODES:
        raise ConfigError(f"mode must be one of {sorted(VALID_MODES)} or None, got {mode!r}.")
    _mode_override = mode


def _reset_mode_override_for_tests() -> None:
    global _mode_override
    _mode_override = None


def _resolve_pandadoc_keys() -> tuple[str, str, str]:
    """Pick the key and template for the active mode.

    Defaults to sandbox: spending one of the 60 production documents has to be
    a deliberate act, not the consequence of a forgotten variable.
    """
    mode = _mode_override or os.environ.get("PANDADOC_MODE", MODE_SANDBOX).strip().lower()
    if mode not in VALID_MODES:
        raise ConfigError(
            f"PANDADOC_MODE must be one of {sorted(VALID_MODES)}, got {mode!r}."
        )
    if mode == MODE_SANDBOX:
        api_key = _required("PANDADOC_SANDBOX_API_KEY")
        # Sandbox lives in its own workspace, so it usually has its own
        # template. Fall back to the production uuid if only one exists.
        template = (
            os.environ.get("PANDADOC_SANDBOX_TEMPLATE_UUID", "").strip()
            or _required("PANDADOC_TEMPLATE_UUID")
        )
    else:
        api_key = _required("PANDADOC_API_KEY")
        template = _required("PANDADOC_TEMPLATE_UUID")
    return mode, api_key, template


@dataclass(frozen=True)
class Settings:
    mode: str
    api_key: str
    template_uuid: str
    webhook_shared_key: str
    api_base: str
    db_path: str
    # Where executed lease PDFs are archived once signing completes: a local
    # directory, or "supabase:<bucket-name>" (see supabase_url/supabase_key).
    archive_dir: str
    # Only used when archive_dir names a supabase: bucket.
    supabase_url: str
    supabase_key: str
    # Ask PandaDoc to email the tenant directly, in addition to handing the
    # landlord a link. False keeps all outbound mail in the landlord's hands.
    pandadoc_sends_email: bool
    # Fallback embedded-session lifetime, used only when a recipient's
    # non-expiring shared_link is unavailable.
    session_lifetime_seconds: int
    # Early-payment discount from lease section 2.
    early_payment_discount: int
    landlords: tuple[Landlord, ...]
    users: tuple[User, ...]

    @property
    def is_sandbox(self) -> bool:
        """Sandbox documents cost nothing and are not legally binding."""
        return self.mode == MODE_SANDBOX

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
        mode, api_key, template_uuid = _resolve_pandadoc_keys()
        # A Postgres DSN if configured (Render's free tier wipes local files
        # on restart), else the local SQLite file exactly as always.
        db_path = os.environ.get("DATABASE_URL", "").strip() or os.environ.get(
            "LGD_DB_PATH", "leases.db"
        )
        return cls(
            mode=mode,
            api_key=api_key,
            template_uuid=template_uuid,
            webhook_shared_key=_required("PANDADOC_WEBHOOK_SHARED_KEY"),
            api_base=os.environ.get(
                "PANDADOC_API_BASE", "https://api.pandadoc.com/public/v1"
            ).rstrip("/"),
            db_path=db_path,
            archive_dir=os.environ.get(
                "LGD_ARCHIVE_DIR", str(REPO_ROOT / "archive")
            ),
            supabase_url=os.environ.get("SUPABASE_URL", "").strip(),
            supabase_key=os.environ.get("SUPABASE_KEY", "").strip(),
            pandadoc_sends_email=_bool("PANDADOC_SENDS_EMAIL", False),
            session_lifetime_seconds=_int("PANDADOC_SESSION_LIFETIME", 1209600),
            early_payment_discount=_int("LGD_EARLY_PAYMENT_DISCOUNT", 50),
            landlords=landlords,
            users=users,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.load()
