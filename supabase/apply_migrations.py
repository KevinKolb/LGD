#!/usr/bin/env python3
"""Apply the SQL files in `supabase/migrations/` to the Supabase database.

    python supabase/apply_migrations.py            # apply, then report
    python supabase/apply_migrations.py --report   # report only, change nothing

Reads `DATABASE_URL` the same way the app does (environment first, then the
repo's `.env`), and applies every `*.sql` file in name order.

There is no migrations ledger table on purpose: each file is written to be
idempotent, so re-running the whole set is the normal thing to do and is how
a database that has drifted gets brought back into line. That matters more
here than in most projects - the schema this talks to is a live production
database, and the one outage this app has actually had came from assuming a
table already had a column it did not (see `users.email` in app/config.py).

Each file runs inside one transaction: a file that fails halfway leaves the
database exactly as it was.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS = Path(__file__).resolve().parent / "migrations"


def database_url() -> str:
    dsn = os.environ.get("DATABASE_URL", "").strip()
    if not dsn:
        from dotenv import dotenv_values

        dsn = (dotenv_values(REPO_ROOT / ".env").get("DATABASE_URL") or "").strip()
    if not dsn:
        raise SystemExit(
            "DATABASE_URL is not set, in the environment or in .env. See "
            "README.md's Deploying section for where the connection string "
            "comes from."
        )
    return dsn


def safe_target(dsn: str) -> str:
    """The host being written to, with the password never printed."""
    return dsn.split("@")[-1]


async def report(connection) -> None:
    """What the database actually looks like now - printed after applying, so
    a run either shows the intended end state or shows what it really is."""
    print("\nTables (RLS = row level security):")
    rows = await connection.fetch(
        "SELECT c.relname, c.relrowsecurity, "
        "(SELECT count(*) FROM pg_policy p WHERE p.polrelid = c.oid) AS policies "
        "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind = 'r' ORDER BY c.relname"
    )
    for row in rows:
        state = "RLS on " if row["relrowsecurity"] else "RLS OFF"
        print(f"  {row['relname']:<16} {state}  {row['policies']} policy/policies")

    print("\nLogins:")
    users = await connection.fetch(
        "SELECT username, role, manager_id, email, person_id, auth_id, "
        "(password_hash <> '') AS has_hash FROM webusers ORDER BY username"
    )
    for user in users:
        linked = "supabase auth" if user["auth_id"] else "no auth identity"
        basic = "pbkdf2" if user["has_hash"] else "-"
        print(
            f"  {user['username']:<24} {user['role']:<9} "
            f"person={'yes' if user['person_id'] else 'MISSING':<7} "
            f"{linked:<16} basic={basic}"
        )

    orphans = await connection.fetchval(
        "SELECT count(*) FROM webusers WHERE person_id IS NULL"
    )
    people = await connection.fetchval("SELECT count(*) FROM people")
    print(f"\n  people rows: {people}   logins with no person: {orphans}")

    triggers = await connection.fetch(
        "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal "
        "AND tgname IN ('webusers_create_person', 'on_auth_user_confirmed') "
        "ORDER BY tgname"
    )
    print("  triggers:", ", ".join(t["tgname"] for t in triggers) or "NONE")


async def main(argv: list[str]) -> int:
    import asyncpg

    dsn = database_url()
    report_only = "--report" in argv

    files = sorted(MIGRATIONS.glob("*.sql"))
    if not files and not report_only:
        raise SystemExit(f"No .sql files in {MIGRATIONS}.")

    # statement_cache_size=0: see the matching comment in app/db.py - required
    # for Supabase's transaction-mode connection pooler.
    connection = await asyncpg.connect(dsn, statement_cache_size=0)
    try:
        print(f"Connected to {safe_target(dsn)}")
        if not report_only:
            for path in files:
                sql = path.read_text(encoding="utf-8")
                print(f"Applying {path.name} ({len(sql.splitlines())} lines)...")
                async with connection.transaction():
                    await connection.execute(sql)
                print(f"  ok: {path.name}")
        await report(connection)
    finally:
        await connection.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1:])))
