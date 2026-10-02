-- ---------------------------------------------------------------------------
-- 013  The rent ledger: each apartment's year, month by month
-- ---------------------------------------------------------------------------
--
-- Run with:  python supabase/apply_migrations.py   (after 001-012), or paste
-- this whole file into the Supabase SQL editor. Idempotent.
--
-- The user, 2026-10-02, with a photo of the paper rent card kept in the
-- binder (one page per apartment per year: date, month, deposit, rent,
-- comments): "Secondary view of rent register should show history. Make a
-- modern version of attached. Should be a paid checkbox too."
--
-- 006's rent_payments already holds one row per apartment per month, with
-- the date received. It gains the rest of the card's columns: the amount
-- of rent, any deposit, a Paid tick and a comment. A row may now have no
-- date (a comment alone, or an amount not yet received): received_on is
-- then '' - the column stays NOT NULL, as in the FastAPI app's table.

alter table public.rent_payments add column if not exists amount text;
alter table public.rent_payments add column if not exists deposit text;
alter table public.rent_payments add column if not exists note text;

-- Paid. Every date recorded before this existed was rent received, so
-- those rows start ticked - once, when the column is added, so a tick
-- taken off later is never put back by running this again.
do $paid$
begin
  if not exists (select 1 from information_schema.columns
                  where table_schema = 'public' and table_name = 'rent_payments' and column_name = 'paid') then
    alter table public.rent_payments add column paid boolean not null default false;
    update public.rent_payments set paid = true where received_on <> '';
  end if;
end
$paid$;

-- One month as the pages see it.
create or replace function public.lgd_rent_json(r public.rent_payments)
returns json
language sql
stable
as $fn$
  select json_build_object('address', r.address, 'unit', r.unit, 'month', r.month,
                           'received_on', nullif(r.received_on, ''),
                           'amount', coalesce(r.amount, ''), 'deposit', coalesce(r.deposit, ''),
                           'paid', r.paid, 'note', coalesce(r.note, ''))
$fn$;
revoke all on function public.lgd_rent_json(public.rent_payments) from public, anon, authenticated;

-- An amount as typed: digits, with cents if any, no "$" or commas.
create or replace function public.lgd_check_amount(amount text)
returns text
language plpgsql
immutable
as $fn$
declare
  clean text := replace(replace(btrim(coalesce(amount, '')), '$', ''), ',', '');
begin
  if clean = '' then
    return null;
  end if;
  if clean !~ '^[0-9]{1,7}([.][0-9]{1,2})?$' then
    raise exception 'That amount does not look right.' using errcode = '22023';
  end if;
  return clean;
end
$fn$;

create or replace function public.lgd_check_date(value text)
returns text
language plpgsql
immutable
as $fn$
declare
  clean text := btrim(coalesce(value, ''));
begin
  if clean = '' then
    return '';
  end if;
  if clean !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' then
    raise exception 'That date does not look right.' using errcode = '22023';
  end if;
  begin
    perform clean::date;
  exception when others then
    raise exception 'That date does not look right.' using errcode = '22023';
  end;
  return clean;
end
$fn$;


-- ---------------------------------------------------------------------------
-- list_rent_payments(month) - as 006, with the new columns
-- ---------------------------------------------------------------------------
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
    select public.lgd_rent_json(r)
      from public.rent_payments r
     where r.manager_id = caller.manager_id
       and r.month = public.lgd_check_month(list_rent_payments.month)
     order by r.address, r.unit;
end
$fn$;
revoke all on function public.list_rent_payments(text) from public, anon;
grant execute on function public.list_rent_payments(text) to authenticated;


-- ---------------------------------------------------------------------------
-- list_rent_history(address, unit, year) - one apartment's year
-- ---------------------------------------------------------------------------
create or replace function public.list_rent_history(address text, unit text, year text)
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
  if year is null or year !~ '^[0-9]{4}$' then
    raise exception 'Choose a year.' using errcode = '22023';
  end if;
  return query
    select public.lgd_rent_json(r)
      from public.rent_payments r
     where r.manager_id = caller.manager_id
       and r.address = btrim(coalesce(list_rent_history.address, ''))
       and r.unit = btrim(coalesce(list_rent_history.unit, ''))
       and r.month like list_rent_history.year || '-%'
     order by r.month;
end
$fn$;
revoke all on function public.list_rent_history(text, text, text) from public, anon;
grant execute on function public.list_rent_history(text, text, text) to authenticated;


-- ---------------------------------------------------------------------------
-- save_rent_entry(...) - one month of the ledger, every column
-- ---------------------------------------------------------------------------
-- A month with nothing in it - no date, amount, deposit, comment or tick -
-- is taken off.
create or replace function public.save_rent_entry(
  month text, address text, unit text default '', received_on text default '',
  amount text default '', deposit text default '', paid boolean default false, note text default ''
)
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
  clean_date text := public.lgd_check_date(received_on);
  clean_amount text := public.lgd_check_amount(amount);
  clean_deposit text := public.lgd_check_amount(deposit);
  clean_note text := nullif(btrim(coalesce(note, '')), '');
  clean_paid boolean := coalesce(paid, false);
  saved public.rent_payments;
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
  if length(coalesce(clean_note, '')) > 500 then
    raise exception 'That comment is too long.' using errcode = '22023';
  end if;
  if clean_date = '' and clean_amount is null and clean_deposit is null and clean_note is null and not clean_paid then
    delete from public.rent_payments r
     where r.manager_id = caller.manager_id and r.address = clean_address
       and r.unit = clean_unit and r.month = clean_month;
    return json_build_object('address', clean_address, 'unit', clean_unit, 'month', clean_month,
                             'received_on', null, 'amount', '', 'deposit', '', 'paid', false, 'note', '');
  end if;
  insert into public.rent_payments
    (manager_id, address, unit, month, received_on, amount, deposit, paid, note, recorded_at, recorded_by)
  values (caller.manager_id, clean_address, clean_unit, clean_month, clean_date, clean_amount,
          clean_deposit, clean_paid, clean_note, public.lgd_now_text(), caller.id)
  on conflict on constraint rent_payments_pkey do update
    set received_on = excluded.received_on, amount = excluded.amount, deposit = excluded.deposit,
        paid = excluded.paid, note = excluded.note,
        recorded_at = excluded.recorded_at, recorded_by = excluded.recorded_by
  returning * into saved;
  return public.lgd_rent_json(saved);
end
$fn$;
revoke all on function public.save_rent_entry(text, text, text, text, text, text, boolean, text) from public, anon;
grant execute on function public.save_rent_entry(text, text, text, text, text, text, boolean, text) to authenticated;


-- ---------------------------------------------------------------------------
-- set_rent_payment(...) - the register's date box, as 006, keeping the rest
-- ---------------------------------------------------------------------------
-- A date is rent received, so it ticks Paid; clearing it takes the tick
-- off. The month's amount, deposit and comment stay; the row goes only
-- when nothing is left in it.
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
  clean_date text := public.lgd_check_date(received_on);
  saved public.rent_payments;
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
  insert into public.rent_payments
    (manager_id, address, unit, month, received_on, paid, recorded_at, recorded_by)
  values (caller.manager_id, clean_address, clean_unit, clean_month, clean_date, clean_date <> '',
          public.lgd_now_text(), caller.id)
  on conflict on constraint rent_payments_pkey do update
    set received_on = excluded.received_on, paid = excluded.paid,
        recorded_at = excluded.recorded_at, recorded_by = excluded.recorded_by
  returning * into saved;
  if clean_date = '' and saved.amount is null and saved.deposit is null and saved.note is null then
    delete from public.rent_payments r
     where r.manager_id = caller.manager_id and r.address = clean_address
       and r.unit = clean_unit and r.month = clean_month;
  end if;
  return public.lgd_rent_json(saved);
end
$fn$;
revoke all on function public.set_rent_payment(text, text, text, text) from public, anon;
grant execute on function public.set_rent_payment(text, text, text, text) to authenticated;

notify pgrst, 'reload schema';
