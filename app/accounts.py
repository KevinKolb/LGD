"""CLI for managing landlords and the people who log in.

    python -m app.accounts init                  # write starter accounts
    python -m app.accounts list                  # who exists, who has a password
    python -m app.accounts set-password kevin    # prompt and store a hash

Passwords are only ever stored as PBKDF2-HMAC-SHA256 hashes.

Normally this reads and writes `accounts.json` - gitignored, since it holds
personal email addresses and password hashes. If `DATABASE_URL` is set (a
Render+Supabase deployment; see `app/config.py`), it operates on the
Postgres `landlords`/`users` tables instead, and `accounts.json` is not
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

from app.auth import hash_password
from app.config import REPO_ROOT, ROLE_ADMIN, ROLE_LANDLORD

DEFAULT_PATH = REPO_ROOT / "accounts.json"
MIN_PASSWORD_LENGTH = 12

# Matches the columns `app.config.preload_accounts_from_postgres` reads.
ACCOUNTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS landlords (
    id           TEXT PRIMARY KEY,
    company      TEXT NOT NULL,
    signer_name  TEXT NOT NULL,
    email        TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    username       TEXT PRIMARY KEY,
    display_name   TEXT NOT NULL,
    role           TEXT NOT NULL,
    landlord_id    TEXT REFERENCES landlords(id),
    password_hash  TEXT NOT NULL DEFAULT ''
);
"""

# Placeholder contact details, not anyone's real information: this file is
# committed to the repo (and so is public if the repo is), while the actual
# `accounts.json` it generates is gitignored. Fill in real names and emails
# in accounts.json after running `init`, never here.
STARTER: dict[str, Any] = {
    "landlords": [
        {
            "id": "lgd",
            "company": "LGD Properties",
            "signer_name": "REPLACE ME",
            "email": "replace-me@example.com",
        },
        {
            "id": "robertson",
            "company": "Orange Street LLC",
            "signer_name": "REPLACE ME",
            "email": "replace-me@example.com",
        },
    ],
    "users": [
        {
            "username": "kevin",
            "display_name": "Kevin Kolb",
            "role": ROLE_ADMIN,
            "password_hash": "",
        },
        {
            "username": "pam",
            "display_name": "REPLACE ME",
            "role": ROLE_LANDLORD,
            "landlord_id": "lgd",
            "password_hash": "",
        },
        {
            "username": "gay",
            "display_name": "REPLACE ME",
            "role": ROLE_LANDLORD,
            "landlord_id": "robertson",
            "password_hash": "",
        },
    ],
}


def load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"{path} does not exist. Run: python -m app.accounts init")
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def cmd_init(path: Path, force: bool) -> int:
    if path.is_file() and not force:
        print(f"{path} already exists. Pass --force to overwrite it.", file=sys.stderr)
        return 1
    save(path, STARTER)
    print(f"Wrote {path}")
    print("\nNobody can log in yet. Set a password for each user:\n")
    for user in STARTER["users"]:
        print(f"    python -m app.accounts set-password {user['username']}")
    print()
    return 0


def cmd_list(path: Path) -> int:
    data = load(path)
    landlords = {entry["id"]: entry for entry in data.get("landlords", [])}

    print("Landlords")
    for landlord in data.get("landlords", []):
        print(f"  {landlord['id']:<12} {landlord['company']}"
              f"  (signs: {landlord['signer_name']} <{landlord['email']}>)")

    print("\nUsers")
    for user in data.get("users", []):
        scope = "all landlords"
        if user.get("role") != ROLE_ADMIN:
            landlord = landlords.get(user.get("landlord_id"), {})
            scope = landlord.get("company", user.get("landlord_id", "?"))
        state = "password set" if user.get("password_hash") else "NO PASSWORD"
        print(f"  {user['username']:<12} {user.get('role', ''):<9} {scope:<26} {state}")
    print()
    return 0


def cmd_set_password(path: Path, username: str) -> int:
    data = load(path)
    for user in data.get("users", []):
        if user["username"] == username:
            break
    else:
        known = ", ".join(u["username"] for u in data.get("users", []))
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


async def _pg_init(dsn: str, force: bool) -> int:
    import asyncpg

    # statement_cache_size=0: see the matching comment in app/db.py - required
    # for Supabase's transaction-mode connection pooler.
    connection = await asyncpg.connect(dsn, statement_cache_size=0)
    try:
        await connection.execute(ACCOUNTS_SCHEMA)
        existing = await connection.fetchval("SELECT count(*) FROM landlords")
        if existing and not force:
            print(f"Postgres already has {existing} landlord row(s). "
                  "Pass --force to overwrite them.", file=sys.stderr)
            return 1
        async with connection.transaction():
            # Overwrite entirely, same as init does to the JSON file - order
            # matters, since users.landlord_id references landlords.
            await connection.execute("DELETE FROM users")
            await connection.execute("DELETE FROM landlords")
            for landlord in STARTER["landlords"]:
                await connection.execute(
                    "INSERT INTO landlords (id, company, signer_name, email) "
                    "VALUES ($1, $2, $3, $4)",
                    landlord["id"], landlord["company"],
                    landlord["signer_name"], landlord["email"],
                )
            for user in STARTER["users"]:
                await connection.execute(
                    "INSERT INTO users "
                    "(username, display_name, role, landlord_id, password_hash) "
                    "VALUES ($1, $2, $3, $4, '')",
                    user["username"], user["display_name"], user["role"],
                    user.get("landlord_id"),
                )
    finally:
        await connection.close()
    print(f"Wrote starter landlords/users rows to {dsn.split('@')[-1]}")
    print("\nNobody can log in yet. Set a password for each user:\n")
    for user in STARTER["users"]:
        print(f"    python -m app.accounts set-password {user['username']}")
    print()
    return 0


async def _pg_list(dsn: str) -> int:
    import asyncpg

    # statement_cache_size=0: see the matching comment in app/db.py - required
    # for Supabase's transaction-mode connection pooler.
    connection = await asyncpg.connect(dsn, statement_cache_size=0)
    try:
        landlord_rows = await connection.fetch(
            "SELECT id, company, signer_name, email FROM landlords ORDER BY id"
        )
        user_rows = await connection.fetch(
            "SELECT username, display_name, role, landlord_id, password_hash "
            "FROM users ORDER BY username"
        )
    finally:
        await connection.close()

    landlords = {row["id"]: row for row in landlord_rows}
    print("Landlords")
    for row in landlord_rows:
        print(f"  {row['id']:<12} {row['company']}"
              f"  (signs: {row['signer_name']} <{row['email']}>)")

    print("\nUsers")
    for row in user_rows:
        scope = "all landlords"
        if row["role"] != ROLE_ADMIN:
            landlord = landlords.get(row["landlord_id"])
            scope = landlord["company"] if landlord else (row["landlord_id"] or "?")
        state = "password set" if row["password_hash"] else "NO PASSWORD"
        print(f"  {row['username']:<12} {row['role']:<9} {scope:<26} {state}")
    print()
    return 0


async def _pg_set_password(dsn: str, username: str) -> int:
    import asyncpg

    # statement_cache_size=0: see the matching comment in app/db.py - required
    # for Supabase's transaction-mode connection pooler.
    connection = await asyncpg.connect(dsn, statement_cache_size=0)
    try:
        row = await connection.fetchrow(
            "SELECT username FROM users WHERE username = $1", username
        )
        if row is None:
            known_rows = await connection.fetch(
                "SELECT username FROM users ORDER BY username"
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
            "UPDATE users SET password_hash = $1 WHERE username = $2",
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

    sub.add_parser("list", help="show landlords and users")

    set_password = sub.add_parser("set-password", help="set a user's password")
    set_password.add_argument("username")

    args = parser.parse_args(argv)

    dsn = os.environ.get("DATABASE_URL", "").strip()
    if dsn:
        if args.command == "init":
            return asyncio.run(_pg_init(dsn, args.force))
        if args.command == "list":
            return asyncio.run(_pg_list(dsn))
        return asyncio.run(_pg_set_password(dsn, args.username))

    if args.command == "init":
        return cmd_init(args.file, args.force)
    if args.command == "list":
        return cmd_list(args.file)
    return cmd_set_password(args.file, args.username)


if __name__ == "__main__":
    raise SystemExit(main())
