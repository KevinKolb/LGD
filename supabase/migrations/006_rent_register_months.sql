-- ---------------------------------------------------------------------------
-- 006  The rent register by month: lease dates, and the rent received
-- ---------------------------------------------------------------------------
--
-- Run with:  python supabase/apply_migrations.py   (after 001-005; the
-- script applies every file in name order). Idempotent, like the others.
--
-- The user, 2026-09-30: the register opens for a chosen month and year; on
-- screen the date each unit's rent was received can be recorded, and it
-- still prints on one 8.5 x 11 sheet; and "mind lease dates if exist when
-- showing who resident is".

-- A resident's lease, when known: "YYYY-MM-DD" text like every other date
-- here. Either may be empty - no start means "since before we recorded it",
-- no end means "still running" - and a resident with neither is shown every
-- month, as before.
alter table public.people add column if not exists lease_start text;
alter table public.people add column if not exists lease_end text;

-- The date each apartment's rent for a month was received. One row per
-- apartment per month, per company; address and unit as
-- documents/properties.json writes them. No row: not recorded yet.
create table if not exists public.rent_payments (
  manager_id  text not null references public.managers(id),
  address     text not null,
  unit        text not null default '',
  month       text not null,            -- "YYYY-MM"
  received_on text not null,            -- "YYYY-MM-DD"
  recorded_at text not null,
  recorded_by text,
  primary key (manager_id, address, unit, month)
);
-- Locked like 004's and 005's tables: 001's loop only covers tables that
-- exist when it runs.
alter table public.rent_payments enable row level security;
revoke all on public.rent_payments from anon, authenticated;


-- A "YYYY-MM" month, or an error in the manager's words.
create or replace function public.lgd_check_month(month text)
returns text
language plpgsql
immutable
as $fn$
begin
  if month is null or month !~ '^[0-9]{4}-(0[1-9]|1[0-2])$' then
    raise exception 'Choose a month and a year.' using errcode = '22023';
  end if;
  return month;
end
$fn$;


-- ---------------------------------------------------------------------------
-- list_residents(month)
-- ---------------------------------------------------------------------------
--
-- 003's version took no month. This one, given "YYYY-MM", leaves out a
-- resident whose lease is recorded and does not cover any day of that
-- month; with no month, or no lease dates, everyone shows, as before.
drop function if exists public.list_residents();
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
             'id', p.id, 'full_name', p.full_name, 'email', p.email, 'phone', p.phone,
             'address', pr.address, 'unit', coalesce(pr.apt, ''),
             'lease_start', p.lease_start, 'lease_end', p.lease_end)
      from public.people p
      join public.properties pr on pr.id = p.property_id
     where p.is_resident
       and (caller.is_admin or p.manager_id is not distinct from caller.manager_id)
       and (first_day is null or coalesce(nullif(p.lease_start, ''), '0000-01-01') <= last_day)
       and (first_day is null or coalesce(nullif(p.lease_end, ''), '9999-12-31') >= first_day)
     order by pr.address, pr.apt, p.full_name;
end
$fn$;
revoke all on function public.list_residents(text) from public, anon;
grant execute on function public.list_residents(text) to authenticated;


-- ---------------------------------------------------------------------------
-- list_rent_payments(month) / set_rent_payment(...)
-- ---------------------------------------------------------------------------
--
-- The caller's own company's dates for a month; and recording one - an
-- empty date takes it back off. Managers and admins only.
create or replace function public.list_rent_payments(month text)
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
    raise exception 'Only a manager or an admin can see the rent register.'
      using errcode = '42501';
  end if;
  return query
    select json_build_object('address', r.address, 'unit', r.unit, 'month', r.month,
                             'received_on', r.received_on)
      from public.rent_payments r
     where r.manager_id = caller.manager_id
       and r.month = public.lgd_check_month(list_rent_payments.month)
     order by r.address, r.unit;
end
$fn$;
revoke all on function public.list_rent_payments(text) from public, anon;
grant execute on function public.list_rent_payments(text) to authenticated;

create or replace function public.set_rent_payment(month text, address text, unit text, received_on text)
returns json
language plpgsql
volatile
security definer
set search_path = public
as $fn$
declare
  caller public.people := public.lgd_caller();
  clean_month text := public.lgd_check_month(month);
  clean_address text := btrim(coalesce(address, ''));
  clean_unit text := btrim(coalesce(unit, ''));
  clean_date text := btrim(coalesce(received_on, ''));
begin
  if caller.id is null or not (caller.is_manager or caller.is_admin) then
    raise exception 'Only a manager or an admin can record rent.' using errcode = '42501';
  end if;
  if caller.manager_id is null then
    raise exception 'Your login is not filed under a company.' using errcode = '22023';
  end if;
  if clean_address = '' or length(clean_address) > 200 or length(clean_unit) > 20 then
    raise exception 'That apartment does not look right.' using errcode = '22023';
  end if;
  if clean_date = '' then
    delete from public.rent_payments r
     where r.manager_id = caller.manager_id and r.address = clean_address
       and r.unit = clean_unit and r.month = clean_month;
    return json_build_object('address', clean_address, 'unit', clean_unit, 'month', clean_month,
                             'received_on', null);
  end if;
  if clean_date !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' then
    raise exception 'That date does not look right.' using errcode = '22023';
  end if;
  begin
    perform clean_date::date;
  exception when others then
    raise exception 'That date does not look right.' using errcode = '22023';
  end;
  insert into public.rent_payments
    (manager_id, address, unit, month, received_on, recorded_at, recorded_by)
  values (caller.manager_id, clean_address, clean_unit, clean_month, clean_date,
          public.lgd_now_text(), caller.id)
  on conflict on constraint rent_payments_pkey do update
    set received_on = excluded.received_on, recorded_at = excluded.recorded_at,
        recorded_by = excluded.recorded_by;
  return json_build_object('address', clean_address, 'unit', clean_unit, 'month', clean_month,
                           'received_on', clean_date);
end
$fn$;
revoke all on function public.set_rent_payment(text, text, text, text) from public, anon;
grant execute on function public.set_rent_payment(text, text, text, text) to authenticated;

notify pgrst, 'reload schema';
