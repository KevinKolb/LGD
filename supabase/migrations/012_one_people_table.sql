-- ---------------------------------------------------------------------------
-- 012  Everyone in one table: people
-- ---------------------------------------------------------------------------
--
-- Run with:  python supabase/apply_migrations.py   (after 001-011), or
-- paste this whole file into the Supabase SQL editor. Idempotent.
--
-- The user, 2026-10-02: "combine all supabase people related tables into
-- one table. logins. applicants. residents. managers. previous admins. put
-- em all in one table and designate their role or roles in the table".
--
-- `people` already held everyone, one row each, with a login as columns
-- (001 merged `webusers` in) and the roles as four yes/no columns. What
-- was left outside it was 008's `person_clients`, the companies each
-- person works for. That becomes `people.clients`, a list of company ids,
-- and the table goes. And a `roles` column spells out the four yes/no
-- columns in words ("manager, resident"), worked out by the database, for
-- reading the table in the dashboard.
--
-- `managers` is not people: it is the table of companies (LGD, Orange
-- Street) - see CLAUDE.md on why it has that name.

alter table public.people add column if not exists clients text[] not null default '{}';

-- The links 008 kept in person_clients, and the company each person is
-- filed under, go into the list; then person_clients is dropped.
do $merge$
begin
  if to_regclass('public.person_clients') is not null then
    execute $q$
      update public.people p
         set clients = (select array(select distinct c from unnest(
                          p.clients || array(select pc.manager_id from public.person_clients pc
                                              where pc.person_id = p.id)) c order by c))
       where exists (select 1 from public.person_clients pc where pc.person_id = p.id)
    $q$;
  end if;
end
$merge$;

update public.people p
   set clients = (select array(select distinct c from unnest(p.clients || array[p.manager_id]) c order by c))
 where p.manager_id is not null and not (p.manager_id = any (p.clients));

drop trigger if exists people_link_client on public.people;
drop table if exists public.person_clients;

-- Whoever is filed under a company - an applicant or resident a manager
-- adds lands in the manager's current one - is linked to it.
create or replace function public.lgd_link_client()
returns trigger
language plpgsql
security definer
set search_path = public
as $fn$
begin
  if new.manager_id is not null and not (new.manager_id = any (coalesce(new.clients, '{}'))) then
    new.clients := coalesce(new.clients, '{}') || new.manager_id;
  end if;
  return new;
end
$fn$;
revoke all on function public.lgd_link_client() from public, anon, authenticated;

drop trigger if exists people_add_client on public.people;
create trigger people_add_client
  before insert or update of manager_id, clients on public.people
  for each row execute function public.lgd_link_client();

-- The roles, in words, from the four columns.
do $roles$
begin
  if not exists (select 1 from information_schema.columns
                  where table_schema = 'public' and table_name = 'people' and column_name = 'roles') then
    alter table public.people add column roles text generated always as (
      -- Plain || and ltrim: a generated column takes only immutable
      -- functions, which concat_ws is not.
      ltrim(case when is_admin then ', admin' else '' end
         || case when is_manager then ', manager' else '' end
         || case when is_resident then ', resident' else '' end
         || case when is_applicant then ', applicant' else '' end, ', ')
    ) stored;
  end if;
end
$roles$;


-- ---------------------------------------------------------------------------
-- list_my_clients() and set_current_client(client), as in 008, from the list
-- ---------------------------------------------------------------------------
create or replace function public.list_my_clients()
returns setof json
language plpgsql
stable
security definer
set search_path = public
as $fn$
declare
  caller public.people := public.lgd_caller();
begin
  if caller.id is null then
    raise exception 'Sign in first.' using errcode = '42501';
  end if;
  return query
    select json_build_object('id', m.id, 'name', m.name,
                             'current', m.id is not distinct from caller.manager_id)
      from public.managers m
     where m.id = any (caller.clients)
     order by m.name;
end
$fn$;
revoke all on function public.list_my_clients() from public, anon;
grant execute on function public.list_my_clients() to authenticated;

create or replace function public.set_current_client(client text)
returns setof json
language plpgsql
volatile
security definer
set search_path = public
as $fn$
declare
  caller public.people := public.lgd_caller();
begin
  if caller.id is null then
    raise exception 'Sign in first.' using errcode = '42501';
  end if;
  if not (client = any (caller.clients)) then
    raise exception 'You are not linked to that client.' using errcode = '42501';
  end if;
  update public.people p set manager_id = client where p.id = caller.id;
  return query select * from public.list_my_clients();
end
$fn$;
revoke all on function public.set_current_client(text) from public, anon;
grant execute on function public.set_current_client(text) to authenticated;

notify pgrst, 'reload schema';
