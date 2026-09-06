"""Configuration: PandaDoc settings from the environment, people from a file.

Secrets and API wiring live in `.env`. Landlords and user logins live in
`accounts.json`, because password hashes and per-user roles do not fit
comfortably in flat environment variables. Both files are gitignored.
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
VALID_ROLES = {ROLE_ADMIN, ROLE_LANDLORD}

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

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

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

        if role == ROLE_LANDLORD:
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
        users.append(
            User(
                username=username,
                display_name=str(entry.get("display_name", username)),
                role=role,
                password_hash=password_hash,
                landlord_id=landlord_id,
            )
        )

    if not users:
        raise ConfigError(f"{path} lists no users, so nobody could log in.")

    duplicates = {u.username for u in users if
                  sum(1 for other in users if other.username == u.username) > 1}
    if duplicates:
        raise ConfigError(f"{path} has duplicate usernames: {sorted(duplicates)}")

    return landlords, tuple(users)


def _resolve_pandadoc_keys() -> tuple[str, str, str]:
    """Pick the key and template for the active mode.

    Defaults to sandbox: spending one of the 60 production documents has to be
    a deliberate act, not the consequence of a forgotten variable.
    """
    mode = os.environ.get("PANDADOC_MODE", MODE_SANDBOX).strip().lower()
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
    # Where executed lease PDFs are archived once signing completes.
    archive_dir: str
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
        accounts_path = Path(
            os.environ.get("LGD_ACCOUNTS_FILE", str(REPO_ROOT / "accounts.json"))
        )
        landlords, users = _load_accounts(accounts_path)
        mode, api_key, template_uuid = _resolve_pandadoc_keys()
        return cls(
            mode=mode,
            api_key=api_key,
            template_uuid=template_uuid,
            webhook_shared_key=_required("PANDADOC_WEBHOOK_SHARED_KEY"),
            api_base=os.environ.get(
                "PANDADOC_API_BASE", "https://api.pandadoc.com/public/v1"
            ).rstrip("/"),
            db_path=os.environ.get("LGD_DB_PATH", "leases.db"),
            archive_dir=os.environ.get(
                "LGD_ARCHIVE_DIR", str(REPO_ROOT / "archive")
            ),
            pandadoc_sends_email=_bool("PANDADOC_SENDS_EMAIL", False),
            session_lifetime_seconds=_int("PANDADOC_SESSION_LIFETIME", 1209600),
            early_payment_discount=_int("LGD_EARLY_PAYMENT_DISCOUNT", 50),
            landlords=landlords,
            users=users,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.load()
