"""CLI for managing managers and the people who log in.

    python -m app.accounts init                     # write starter accounts
    python -m app.accounts list                     # who exists, who has a password
    python -m app.accounts set-password kevin       # prompt and store a hash
    python -m app.accounts set-email kevin a@b.com  # let that address claim it
    python -m app.accounts link-people              # every login gets a person row

Passwords are only ever stored as PBKDF2-HMAC-SHA256 hashes.

Normally this reads and writes `accounts.json` - gitignored, since it holds
personal email addresses and password hashes. If `DATABASE_URL` is set (a
Render+Supabase deployment; see `app/config.py`), it operates on the
Postgres `managers`/`users` tables instead, and `accounts.json` is not
touched - the two are never both in play in a single run.
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import sys
from pathlib import Path
from typing import Any

from app import db
from app.auth import hash_password
from app.config import REPO_ROOT, ROLE_ADMIN, ROLE_MANAGER

DEFAULT_PATH = REPO_ROOT / "accounts.json"
MIN_PASSWORD_LENGTH = 12

# Matches the columns `app.config.preload_accounts_from_postgres` reads.
ACCOUNTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS managers (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    signer_name  TEXT NOT NULL,
    email        TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS webusers (
    username       TEXT PRIMARY KEY,
    display_name   TEXT NOT NULL,
    role           TEXT NOT NULL,
    manager_id    TEXT REFERENCES managers(id),
    password_hash  TEXT NOT NULL DEFAULT '',
    email          TEXT,
    -- The Supabase Auth identity that checks this person's password on the
    -- website, and their row in the `people` directory. Both are filled in
    -- by supabase/migrations/001_auth_people_rls.sql and its triggers; this
    -- CREATE only matters for a database being made from scratch.
    auth_id        UUID,
    person_id      TEXT
);
"""

# Placeholder contact details, not anyone's real information: this file is
# committed to the repo (and so is public if the repo is), while the actual
# `accounts.json` it generates is gitignored. Fill in real names and emails
# in accounts.json after running `init`, never here.
STARTER: dict[str, Any] = {
    "managers": [
        {
            "id": "lgd",
            "name": "LGD Properties",
            "signer_name": "REPLACE ME",
            "email": "replace-me@example.com",
        },
        {
            "id": "robertson",
            "name": "Orange Street LLC",
            "signer_name": "REPLACE ME",
            "email": "replace-me@example.com",
        },
    ],
    "webusers": [
        {
            "username": "kevin",
            "display_name": "Kevin Kolb",
            "role": ROLE_ADMIN,
            "password_hash": "",
            "email": "replace-me@example.com",
        },
        {
            "username": "pam",
            "display_name": "REPLACE ME",
            "role": ROLE_MANAGER,
            "manager_id": "lgd",
            "password_hash": "",
            "email": "replace-me@example.com",
        },
        {
            "username": "gay",
            "display_name": "REPLACE ME",
            "role": ROLE_MANAGER,
            "manager_id": "robertson",
            "password_hash": "",
            "email": "replace-me@example.com",
        },
    ],
}


def load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"{path} does not exist. Run: python -m app.accounts init")
    return migrate_keys(json.loads(path.read_text(encoding="utf-8")))


def migrate_keys(data: dict[str, Any]) -> dict[str, Any]:
    """Accept a file written before the landlords -> managers and
    users -> webusers renames, and hand back the current shape.

    The old spellings below - "landlords", "users", "company", "landlord_id" -
    are historical data, not vocabulary to keep in step with the rest of the
    code. Renaming them to match today's words is what would break this.

    This file is gitignored and holds real password hashes, so it cannot be
    migrated by editing something committed - and a login that stops working
    because a key was renamed is the worst failure this project has. Reading
    both spellings costs nothing; the next `save()` writes the new one.
    """
    if "managers" not in data and "landlords" in data:
        data["managers"] = data.pop("landlords")
    if "webusers" not in data and "users" in data:
        data["webusers"] = data.pop("users")
    for manager in data.get("managers", []):
        if "name" not in manager and "company" in manager:
            manager["name"] = manager.pop("company")
    for user in data.get("webusers", []):
        if "manager_id" not in user and "landlord_id" in user:
            user["manager_id"] = user.pop("landlord_id")
    return data


def save(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


async def set_password_hash(username: str, new_hash: str) -> bool:
    """Write an already-hashed password for `username` to whichever backend
    is active (same DATABASE_URL check as everywhere else). Returns False if
    no such user exists.

    For the web dashboard's own "change my password" feature (see
    app/main.py) - deliberately takes a hash, not a raw password, so the
    caller controls hashing/validation and this stays a pure storage write.
    The caller is also responsible for refreshing any cached Settings/
    accounts afterward; this function only writes the durable store.
    """
    dsn = os.environ.get("DATABASE_URL", "").strip()
    if dsn:
        import asyncpg

        connection = await asyncpg.connect(dsn, statement_cache_size=0)
        try:
            result = await connection.execute(
                "UPDATE webusers SET password_hash = $1 WHERE username = $2",
                new_hash, username,
            )
        finally:
            await connection.close()
        return result != "UPDATE 0"

    path = Path(os.environ.get("LGD_ACCOUNTS_FILE", str(DEFAULT_PATH)))
    if not path.is_file():
        return False
    # migrate_keys, not a bare json.loads: this runs against whatever file
    # is on disk, which may still use the pre-rename key names.
    data = migrate_keys(json.loads(path.read_text(encoding="utf-8")))
    for user in data.get("webusers", []):
        if user["username"] == username:
            user["password_hash"] = new_hash
            save(path, data)
            return True
    return False


def cmd_init(path: Path, force: bool) -> int:
    if path.is_file() and not force:
        print(f"{path} already exists. Pass --force to overwrite it.", file=sys.stderr)
        return 1
    save(path, STARTER)
    print(f"Wrote {path}")
    # Every login is also a person. On Supabase a trigger guarantees that;
    # here it is this call, and `link-people` re-runs it at any time.
    cmd_link_people(path)
    print("\nNobody can log in yet. Set a password for each user:\n")
    for user in STARTER["webusers"]:
        print(f"    python -m app.accounts set-password {user['username']}")
    print()
    return 0


def cmd_list(path: Path) -> int:
    data = load(path)
    managers = {entry["id"]: entry for entry in data.get("managers", [])}

    print("Managers")
    for manager in data.get("managers", []):
        print(f"  {manager['id']:<12} {manager['name']}"
              f"  (signs: {manager['signer_name']} <{manager['email']}>)")

    print("\nUsers")
    for user in data.get("webusers", []):
        scope = "all managers"
        if user.get("role") != ROLE_ADMIN:
            manager = managers.get(user.get("manager_id"), {})
            scope = manager.get("name", user.get("manager_id", "?"))
        state = "password set" if user.get("password_hash") else "NO PASSWORD"
        email = user.get("email") or "no email"
        print(f"  {user['username']:<12} {user.get('role', ''):<9} {scope:<26} {state:<14} {email}")
    print()
    return 0


def cmd_set_password(path: Path, username: str) -> int:
    data = load(path)
    for user in data.get("webusers", []):
        if user["username"] == username:
            break
    else:
        known = ", ".join(u["username"] for u in data.get("webusers", []))
        print(f"No user {username!r}. Known users: {known}", file=sys.stderr)
        return 1

    password = getpass.getpass(f"New password for {username}: ")
    if len(password) < MIN_PASSWORD_LENGTH:
        print(f"Refusing: use at least {MIN_PASSWORD_LENGTH} characters.",
              file=sys.stderr)
        return 1
    if password != getpass.getpass("Confirm: "):
        print("Passwords did not match.", file=sys.stderr)
        return 1

    user["password_hash"] = hash_password(password)
    save(path, data)
    print(f"Password set for {username}.")
    return 0


def records_db_path() -> str:
    """Where the `people` table lives, resolved the same way app/config.py
    does it - a Postgres DSN if DATABASE_URL is set, else the local SQLite
    file. This CLI otherwise only touches accounts, but a login is not
    complete without its person row."""
    return os.environ.get("DATABASE_URL", "").strip() or os.environ.get(
        "LGD_DB_PATH", "leases.db"
    )


def cmd_link_people(path: Path) -> int:
    """Give every login in accounts.json a row in `people`, if it lacks one.

    This is the local-backend half of the rule the Supabase database enforces
    with a trigger: every user is also a person. Safe to re-run - it only
    touches users whose `person_id` is missing - so it doubles as the
    backfill for an accounts.json written before that rule existed.
    """
    data = load(path)
    db_path = records_db_path()
    # The records database may not exist yet - this command is the first
    # thing `init` runs, on a machine where nothing has started the app.
    asyncio.run(db.init(db_path))
    created = 0
    for user in data.get("webusers", []):
        if user.get("person_id"):
            continue
        person_id = asyncio.run(
            db.create_person(
                db_path,
                role=user.get("role", ROLE_MANAGER),
                full_name=user.get("display_name") or user["username"],
                email=user.get("email"),
                manager_id=user.get("manager_id"),
            )
        )
        user["person_id"] = person_id
        created += 1
        print(f"  {user['username']:<12} -> person {person_id}")
    if created:
        save(path, data)
    print(f"{created} person row(s) created; "
          f"{len(data.get('users', [])) - created} already linked.")
    return 0


def cmd_set_email(path: Path, username: str, email: str) -> int:
    data = load(path)
    for user in data.get("webusers", []):
        if user["username"] == username:
            user["email"] = email
            save(path, data)
            print(f"{username} now has email {email}.")
            return 0
    known = ", ".join(u["username"] for u in data.get("webusers", []))
    print(f"No user {username!r}. Known users: {known}", file=sys.stderr)
    return 1


async def _pg_set_email(dsn: str, username: str, email: str) -> int:
    import asyncpg

    # statement_cache_size=0: see the matching comment in app/db.py - required
    # for Supabase's transaction-mode connection pooler.
    connection = await asyncpg.connect(dsn, statement_cache_size=0)
    try:
        result = await connection.execute(
            "UPDATE webusers SET email = $1 WHERE username = $2", email, username
        )
    finally:
        await connection.close()
    if result == "UPDATE 0":
        print(f"No user {username!r}.", file=sys.stderr)
        return 1
    print(f"{username} now has email {email}.")
    print()
    print(
        "That address can now claim this account: sign up with it at the "
        "site's login page and confirm the email, and this row - role and "
        "manager included - becomes that login. See "
        "supabase/migrations/001_auth_people_rls.sql."
    )
    return 0


async def _pg_link_people(dsn: str) -> int:
    """Report on the users <-> people link. Unlike the local backend, nothing
    needs doing here: the database creates the person row itself, in a
    BEFORE INSERT trigger on `users`. This just says whether that is true."""
    import asyncpg

    connection = await asyncpg.connect(dsn, statement_cache_size=0)
    try:
        has_column = await connection.fetchval(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'webusers' AND column_name = 'person_id'"
        )
        if not has_column:
            print("This database has not had supabase/migrations applied yet.",
                  file=sys.stderr)
            print("Run: python supabase/apply_migrations.py", file=sys.stderr)
            return 1
        rows = await connection.fetch(
            "SELECT u.username, u.person_id, p.full_name FROM webusers u "
            "LEFT JOIN people p ON p.id = u.person_id ORDER BY u.username"
        )
    finally:
        await connection.close()
    missing = 0
    for row in rows:
        if row["person_id"]:
            print(f"  {row['username']:<24} -> {row['full_name']}")
        else:
            missing += 1
            print(f"  {row['username']:<24} -> NO PERSON ROW")
    print()
    print(f"{len(rows) - missing} of {len(rows)} login(s) linked.")
    return 1 if missing else 0


async def _pg_init(dsn: str, force: bool) -> int:
    import asyncpg

    # statement_cache_size=0: see the matching comment in app/db.py - required
    # for Supabase's transaction-mode connection pooler.
    connection = await asyncpg.connect(dsn, statement_cache_size=0)
    try:
        await connection.execute(ACCOUNTS_SCHEMA)
        existing = await connection.fetchval("SELECT count(*) FROM managers")
        if existing and not force:
            print(f"Postgres already has {existing} manager row(s). "
                  "Pass --force to overwrite them.", file=sys.stderr)
            return 1
        async with connection.transaction():
            # Overwrite entirely, same as init does to the JSON file - order
            # matters, since users.manager_id references managers.
            await connection.execute("DELETE FROM webusers")
            await connection.execute("DELETE FROM managers")
            for manager in STARTER["managers"]:
                await connection.execute(
                    "INSERT INTO managers (id, name, signer_name, email) "
                    "VALUES ($1, $2, $3, $4)",
                    manager["id"], manager["name"],
                    manager["signer_name"], manager["email"],
                )
            for user in STARTER["webusers"]:
                await connection.execute(
                    "INSERT INTO webusers "
                    "(username, display_name, role, manager_id, password_hash, email) "
                    "VALUES ($1, $2, $3, $4, '', $5)",
                    user["username"], user["display_name"], user["role"],
                    user.get("manager_id"), user.get("email"),
                )
    finally:
        await connection.close()
    print(f"Wrote starter managers/users rows to {dsn.split('@')[-1]}")
    print("\nNobody can log in yet. Set a password for each user:\n")
    for user in STARTER["webusers"]:
        print(f"    python -m app.accounts set-password {user['username']}")
    print()
    return 0


async def _pg_list(dsn: str) -> int:
    import asyncpg

    # statement_cache_size=0: see the matching comment in app/db.py - required
    # for Supabase's transaction-mode connection pooler.
    connection = await asyncpg.connect(dsn, statement_cache_size=0)
    try:
        manager_rows = await connection.fetch(
            "SELECT id, name, signer_name, email FROM managers ORDER BY id"
        )
        user_rows = await connection.fetch(
            "SELECT username, display_name, role, manager_id, password_hash, "
            "email FROM webusers ORDER BY username"
        )
    finally:
        await connection.close()

    managers = {row["id"]: row for row in manager_rows}
    print("Managers")
    for row in manager_rows:
        print(f"  {row['id']:<12} {row['name']}"
              f"  (signs: {row['signer_name']} <{row['email']}>)")

    print("\nUsers")
    for row in user_rows:
        scope = "all managers"
        if row["role"] != ROLE_ADMIN:
            manager = managers.get(row["manager_id"])
            scope = manager["name"] if manager else (row["manager_id"] or "?")
        state = "password set" if row["password_hash"] else "NO PASSWORD"
        email = row["email"] or "no email"
        print(f"  {row['username']:<12} {row['role']:<9} {scope:<26} {state:<14} {email}")
    print()
    return 0


async def _pg_set_password(dsn: str, username: str) -> int:
    import asyncpg

    # statement_cache_size=0: see the matching comment in app/db.py - required
    # for Supabase's transaction-mode connection pooler.
    connection = await asyncpg.connect(dsn, statement_cache_size=0)
    try:
        row = await connection.fetchrow(
            "SELECT username FROM webusers WHERE username = $1", username
        )
        if row is None:
            known_rows = await connection.fetch(
                "SELECT username FROM webusers ORDER BY username"
            )
            known = ", ".join(r["username"] for r in known_rows)
            print(f"No user {username!r}. Known users: {known}", file=sys.stderr)
            return 1

        password = getpass.getpass(f"New password for {username}: ")
        if len(password) < MIN_PASSWORD_LENGTH:
            print(f"Refusing: use at least {MIN_PASSWORD_LENGTH} characters.",
                  file=sys.stderr)
            return 1
        if password != getpass.getpass("Confirm: "):
            print("Passwords did not match.", file=sys.stderr)
            return 1

        await connection.execute(
            "UPDATE webusers SET password_hash = $1 WHERE username = $2",
            hash_password(password), username,
        )
    finally:
        await connection.close()
    print(f"Password set for {username}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.accounts")
    parser.add_argument("--file", type=Path, default=DEFAULT_PATH,
                        help=f"accounts file (default: {DEFAULT_PATH})")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="write a starter accounts.json")
    init.add_argument("--force", action="store_true", help="overwrite an existing file")

    sub.add_parser("list", help="show managers and users")

    set_password = sub.add_parser("set-password", help="set a user's password")
    set_password.add_argument("username")

    set_email = sub.add_parser(
        "set-email",
        help="set a user's email, so that address can claim the account",
    )
    set_email.add_argument("username")
    set_email.add_argument("email")

    sub.add_parser(
        "link-people", help="give every login a row in the people directory"
    )

    args = parser.parse_args(argv)

    dsn = os.environ.get("DATABASE_URL", "").strip()
    if dsn:
        if args.command == "init":
            return asyncio.run(_pg_init(dsn, args.force))
        if args.command == "list":
            return asyncio.run(_pg_list(dsn))
        if args.command == "set-email":
            return asyncio.run(_pg_set_email(dsn, args.username, args.email))
        if args.command == "link-people":
            return asyncio.run(_pg_link_people(dsn))
        return asyncio.run(_pg_set_password(dsn, args.username))

    if args.command == "init":
        return cmd_init(args.file, args.force)
    if args.command == "list":
        return cmd_list(args.file)
    if args.command == "set-email":
        return cmd_set_email(args.file, args.username, args.email)
    if args.command == "link-people":
        return cmd_link_people(args.file)
    return cmd_set_password(args.file, args.username)


if __name__ == "__main__":
    raise SystemExit(main())
