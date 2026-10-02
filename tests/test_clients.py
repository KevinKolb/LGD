"""Logins linked to several clients (the user, 2026-10-02): migration 008."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SQL = (ROOT / "supabase" / "migrations" / "008_clients.sql").read_text(encoding="utf-8")


def test_the_link_table_is_locked_to_the_browser():
    assert "create table if not exists public.person_clients" in SQL
    assert "alter table public.person_clients enable row level security;" in SQL
    assert "revoke all on public.person_clients from anon, authenticated;" in SQL


def test_a_login_switches_only_to_a_client_it_is_linked_to():
    switch = SQL[SQL.index("create or replace function public.set_current_client"):]
    switch = switch[:switch.index("$fn$;")]
    assert "where pc.person_id = caller.id and pc.manager_id = client" in switch
    assert "update public.people p set manager_id = client where p.id = caller.id;" in switch
    for function in ("list_my_clients()", "set_current_client(text)"):
        assert f"revoke all on function public.{function} from public, anon;" in SQL
        assert f"grant execute on function public.{function} to authenticated;" in SQL


def test_the_clients_names():
    assert "('lgd', 'LGD (Lower Garden District Properties), Inc.', '', '')" in SQL
    assert "('robertson', 'Orange Street, Inc.', '', '')" in SQL


def test_lists_show_only_the_current_client_even_to_an_admin():
    lists = SQL[SQL.index("Lists show the client being worked in"):]
    assert lists.count("and p.manager_id is not distinct from caller.manager_id") == 2
    assert "caller.is_admin or p.manager_id" not in lists
