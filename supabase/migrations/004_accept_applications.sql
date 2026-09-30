-- ---------------------------------------------------------------------------
-- 004  Which apartments are accepting applications
-- ---------------------------------------------------------------------------
--
-- Run with:  python supabase/apply_migrations.py   (after 001-003; the
-- script applies every file in name order). Idempotent, like the others.
--
-- The user, 2026-09-30: a manager-page section, Accept Applications, whose
-- popup shows every apartment and lets the manager choose which ones take
-- applications. One row per apartment accepting them, per company; an
-- apartment not listed is not accepting. Address and unit are written as
-- documents/properties.json writes them ("1558 Camp St.", "A"; the unit
-- empty for a single house), which is where the popup's list comes from.

create table if not exists public.open_apartments (
  manager_id text not null references public.managers(id),
  address    text not null,
  unit       text not null default '',
  opened_at  text not null,
  primary key (manager_id, address, unit)
);

-- 001 locks every table that exists when it runs; this one is created
-- after it, so it is locked here. Supabase grants a new public table to
-- anon and authenticated by default - revoked, so the browser reaches it
-- only through the two functions below.
alter table public.open_apartments enable row level security;
revoke all on public.open_apartments from anon, authenticated;


-- ---------------------------------------------------------------------------
-- list_open_apartments
-- ---------------------------------------------------------------------------
--
-- The caller's own company's apartments accepting applications - for an
-- admin too, since the popup edits the company they belong to.
create or replace function public.list_open_apartments()
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
    raise exception 'Only a manager or an admin can see which apartments take applications.'
      using errcode = '42501';
  end if;
  return query
    select json_build_object('address', o.address, 'unit', o.unit, 'opened_at', o.opened_at)
      from public.open_apartments o
     where o.manager_id = caller.manager_id
     order by o.address, o.unit;
end
$fn$;
revoke all on function public.list_open_apartments() from public, anon;
grant execute on function public.list_open_apartments() to authenticated;


-- ---------------------------------------------------------------------------
-- set_open_apartments
-- ---------------------------------------------------------------------------
--
-- Replaces the caller's company's list with `apartments`, a JSON array of
-- {"address": ..., "unit": ...}. An apartment already open keeps the date
-- it was opened; one left out is closed. Always the caller's own company -
-- never one the browser sends.
create or replace function public.set_open_apartments(apartments json)
returns setof json
language plpgsql
volatile
security definer
set search_path = public
as $fn$
declare
  caller public.people := public.lgd_caller();
  item json;
  clean_address text;
  clean_unit text;
begin
  if caller.id is null or not (caller.is_manager or caller.is_admin) then
    raise exception 'Only a manager or an admin can choose which apartments take applications.'
      using errcode = '42501';
  end if;
  if caller.manager_id is null then
    raise exception 'Your login is not filed under a company.' using errcode = '22023';
  end if;
  if apartments is null or json_typeof(apartments) <> 'array' then
    raise exception 'Send a list of apartments.' using errcode = '22023';
  end if;
  if json_array_length(apartments) > 500 then
    raise exception 'That is too many apartments.' using errcode = '22023';
  end if;

  for item in select * from json_array_elements(apartments) loop
    clean_address := btrim(coalesce(item ->> 'address', ''));
    clean_unit := btrim(coalesce(item ->> 'unit', ''));
    if clean_address = '' or length(clean_address) > 200 or length(clean_unit) > 20 then
      raise exception 'One of those apartments does not look right.' using errcode = '22023';
    end if;
  end loop;

  with wanted as (
    select distinct btrim(x ->> 'address') as address, btrim(coalesce(x ->> 'unit', '')) as unit
      from json_array_elements(apartments) x
  )
  delete from public.open_apartments o
   where o.manager_id = caller.manager_id
     and not exists (select 1 from wanted w where w.address = o.address and w.unit = o.unit);

  insert into public.open_apartments (manager_id, address, unit, opened_at)
  select distinct caller.manager_id, btrim(x ->> 'address'), btrim(coalesce(x ->> 'unit', '')),
         public.lgd_now_text()
    from json_array_elements(apartments) x
  on conflict (manager_id, address, unit) do nothing;

  return query select * from public.list_open_apartments();
end
$fn$;
revoke all on function public.set_open_apartments(json) from public, anon;
grant execute on function public.set_open_apartments(json) to authenticated;

-- ---------------------------------------------------------------------------
-- accepting_applications - anyone, signed in or not
-- ---------------------------------------------------------------------------
--
-- The applicant page shows its Apply button only while some property is
-- accepting applications (the user, 2026-09-30), and a statement instead
-- otherwise - asked before anyone has signed in. It answers yes or no and
-- nothing more: not which apartments, nor whose.
create or replace function public.accepting_applications()
returns boolean
language sql
stable
security definer
set search_path = public
as $fn$
  select exists (select 1 from public.open_apartments)
$fn$;
revoke all on function public.accepting_applications() from public;
grant execute on function public.accepting_applications() to anon, authenticated;

notify pgrst, 'reload schema';
