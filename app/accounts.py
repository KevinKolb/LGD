"""CLI for managing `accounts.json` - the landlords and the people who log in.

    python -m app.accounts init                  # write a starter accounts.json
    python -m app.accounts list                  # who exists, who has a password
    python -m app.accounts set-password kevin    # prompt and store a hash

Passwords are only ever stored as PBKDF2-HMAC-SHA256 hashes. The file holds
personal email addresses and password hashes, so it is gitignored.
"""
from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path
from typing import Any

from app.auth import hash_password
from app.config import REPO_ROOT, ROLE_ADMIN, ROLE_LANDLORD

DEFAULT_PATH = REPO_ROOT / "accounts.json"
MIN_PASSWORD_LENGTH = 12

STARTER: dict[str, Any] = {
    "landlords": [
        {
            "id": "lgd",
            "company": "LGD Properties",
            "signer_name": "Pam Hartnett",
            "email": "pamelahartnett@yahoo.com",
        },
        {
            "id": "robertson",
            "company": "Orange Street LLC",
            "signer_name": "Gay Robertson",
            "email": "hrobertson@yahoo.com",
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
            "display_name": "Pam Hartnett",
            "role": ROLE_LANDLORD,
            "landlord_id": "lgd",
            "password_hash": "",
        },
        {
            "username": "gay",
            "display_name": "Gay Robertson",
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
    if args.command == "init":
        return cmd_init(args.file, args.force)
    if args.command == "list":
        return cmd_list(args.file)
    return cmd_set_password(args.file, args.username)


if __name__ == "__main__":
    raise SystemExit(main())
