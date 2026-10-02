-- ---------------------------------------------------------------------------
-- 008  Clients: a login may work for several management companies
-- ---------------------------------------------------------------------------
--
-- Run with:  python supabase/apply_migrations.py   (after 001-007; the
-- script applies every file in name order). Idempotent, like the others.
--
-- The user, 2026-10-02: "make site available to different clients. logins
-- will be linked to clients ... logins can be linked to more than client."
-- A client is a row of `managers` (the management companies; the name is
-- the 2026-09-08 rename's, see CLAUDE.md). Until now a person belonged to
-- one, `people.manager_id`. Now `person_clients` lists every client a
-- person is linked to, and `people.manager_id` is the one they are working
-- in right now - so every function since 002, which scopes to
-- caller.manager_id, follows the client the manager has picked without a
-- change of its own.

-- The clients' names (the user, same day). 'robertson' is the id the
-- second company has had since the starter accounts; an id is data, so it
-- stays, and only the name shown changes.
insert into public.managers (id, name, signer_name, email)
values ('lgd', 'LGD (Lower Garden District Properties), Inc.', '', ''),
       ('robertson', 'Orange Street, Inc.', '', '')
on conflict (id) do update set name = excluded.name;

create table if not exists public.person_clients (
  person_id  text not null references public.people(id) on delete cascade,
  manager_id text not null references public.managers(id),
  primary key (person_id, manager_id)
);
-- Locked like 004's to 007's tables: 001's loop only covers tables that
-- exist when it runs. The browser reaches it through the functions below.
alter table public.person_clients enable row level security;
revoke all on public.person_clients from anon, authenticated;

-- Everyone already filed under a client is linked to it.
insert into public.person_clients (person_id, manager_id)
select p.id, p.manager_id from public.people p where p.manager_id is not null
on conflict do nothing;

-- And whoever is filed under one from now on - an applicant or resident a
-- manager adds lands in the manager's current client - is linked to it.
create or replace function public.lgd_link_client()
returns trigger
language plpgsql
security definer
set search_path = public
as $fn$
begin
  if new.manager_id is not null then
    insert into public.person_clients (person_id, manager_id)
    values (new.id, new.manager_id)
    on conflict do nothing;
  end if;
  return new;
end
$fn$;
revoke all on function public.lgd_link_client() from public, anon, authenticated;

drop trigger if exists people_link_client on public.people;
create trigger people_link_client
  after insert or update of manager_id on public.people
  for each row execute function public.lgd_link_client();


-- ---------------------------------------------------------------------------
-- list_my_clients() - the clients the signed-in person is linked to
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
      from public.person_clients pc
      join public.managers m on m.id = pc.manager_id
     where pc.person_id = caller.id
     order by m.name;
end
$fn$;
revoke all on function public.list_my_clients() from public, anon;
grant execute on function public.list_my_clients() to authenticated;


-- ---------------------------------------------------------------------------
-- set_current_client(client) - work in another of one's own clients
-- ---------------------------------------------------------------------------
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
  if not exists (select 1 from public.person_clients pc
                  where pc.person_id = caller.id and pc.manager_id = client) then
    raise exception 'You are not linked to that client.' using errcode = '42501';
  end if;
  update public.people p set manager_id = client where p.id = caller.id;
  return query select * from public.list_my_clients();
end
$fn$;
revoke all on function public.set_current_client(text) from public, anon;
grant execute on function public.set_current_client(text) to authenticated;


-- ---------------------------------------------------------------------------
-- Lists show the client being worked in - an admin's too
-- ---------------------------------------------------------------------------
--
-- 002's list_applicants and 007's list_residents (which feeds the rent
-- register) showed an admin every company at once. With a login linked to
-- several clients that mixed them - LGD's residents on Orange Street's
-- register - so now everyone sees the current client's, and an admin
-- switches client to see another's. Otherwise as in 002 and 007.
create or replace function public.list_applicants(archived boolean default false)
returns setof json
language plpgsql
stable
security definer
set search_path = public
as $fn$
declare
  caller public.people := public.lgd_caller();
begin
  if caller.id is null or not (caller.is_manager or caller.is_admin) then
    raise exception 'Only a manager or an admin can see applicants.'
      using errcode = '42501';
  end if;
  return query
    select public.lgd_applicant_json(p)
      from public.people p
     where p.is_applicant
       and (p.archived_at is not null) = coalesce(archived, false)
       and p.manager_id is not distinct from caller.manager_id
     order by coalesce(p.archived_at, p.created_at) desc
     limit 500;
end
$fn$;
revoke all on function public.list_applicants(boolean) from public, anon;
grant execute on function public.list_applicants(boolean) to authenticated;

create or replace function public.list_residents(month text default null)
returns setof json
language plpgsql
stable
security definer
set search_path = public
as $fn$
declare
  caller public.people := public.lgd_caller();
  first_day text;
  last_day text;
begin
  if caller.id is null or not (caller.is_manager or caller.is_admin) then
    raise exception 'Only a manager or an admin can see the residents.'
      using errcode = '42501';
  end if;
  if month is not null then
    first_day := public.lgd_check_month(month) || '-01';
    last_day := to_char((first_day::date + interval '1 month' - interval '1 day')::date, 'YYYY-MM-DD');
  end if;
  return query
    select json_build_object(
             'id', p.id, 'full_name', p.full_name,
             'first_name', coalesce(p.first_name, ''), 'last_name', coalesce(p.last_name, ''),
             'email', p.email, 'phone', p.phone,
             'address', pr.address, 'unit', coalesce(pr.apt, ''),
             'lease_start', p.lease_start, 'lease_end', p.lease_end,
             'has_login', p.auth_id is not null or coalesce(p.password_hash, '') <> '')
      from public.people p
      join public.properties pr on pr.id = p.property_id
     where p.is_resident
       and p.manager_id is not distinct from caller.manager_id
       and (first_day is null or coalesce(nullif(p.lease_start, ''), '0000-01-01') <= last_day)
       and (first_day is null or coalesce(nullif(p.lease_end, ''), '9999-12-31') >= first_day)
     order by pr.address, pr.apt, p.full_name;
end
$fn$;
revoke all on function public.list_residents(text) from public, anon;
grant execute on function public.list_residents(text) to authenticated;

notify pgrst, 'reload schema';
