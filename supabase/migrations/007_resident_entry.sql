-- ---------------------------------------------------------------------------
-- 007  Resident Entry: a manager puts residents in apartments
-- ---------------------------------------------------------------------------
--
-- Run with:  python supabase/apply_migrations.py   (after 001-006; the
-- script applies every file in name order). Idempotent, like the others.
--
-- The user, 2026-09-30: "to get the rent register up and running for 10/1
-- add a temporary manager section called resident entry. let there be more
-- than one resident per unit. let manager provide as little info as they
-- can, all optional ... this will expand to user accounts at some point."
--
-- Only the apartment is needed - without it nobody can appear on the
-- register. Names, email, phone and lease dates are all optional. A
-- resident is an ordinary `people` row with is_resident set and a
-- property_id, so one entered with an email is the very row their login
-- attaches to when they sign up (001's trigger), and the rent register
-- (006's list_residents) shows them without any change of its own.


-- The `properties` row for an apartment in the caller's company, made if
-- it is not there yet. Address and unit as documents/properties.json writes
-- them; the unit empty for a single house.
create or replace function public.lgd_property_id(manager text, address text, unit text)
returns text
language plpgsql
volatile
security definer
set search_path = public
as $fn$
declare
  found_id text;
begin
  select pr.id into found_id from public.properties pr
   where pr.manager_id = manager and pr.address = lgd_property_id.address
     and coalesce(pr.apt, '') = coalesce(lgd_property_id.unit, '')
   order by pr.created_at limit 1;
  if found_id is null then
    insert into public.properties (id, manager_id, address, apt, created_at)
    values (public.lgd_new_id(), manager, lgd_property_id.address,
            nullif(lgd_property_id.unit, ''), public.lgd_now_text())
    returning id into found_id;
  end if;
  return found_id;
end
$fn$;
revoke all on function public.lgd_property_id(text, text, text) from public, anon, authenticated;


-- ---------------------------------------------------------------------------
-- list_residents(month) - now with first and last name, for editing
-- ---------------------------------------------------------------------------
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
       and (caller.is_admin or p.manager_id is not distinct from caller.manager_id)
       and (first_day is null or coalesce(nullif(p.lease_start, ''), '0000-01-01') <= last_day)
       and (first_day is null or coalesce(nullif(p.lease_end, ''), '9999-12-31') >= first_day)
     order by pr.address, pr.apt, p.full_name;
end
$fn$;
revoke all on function public.list_residents(text) from public, anon;
grant execute on function public.list_residents(text) to authenticated;


-- ---------------------------------------------------------------------------
-- save_resident - add one, or (with person_id) change one
-- ---------------------------------------------------------------------------
--
-- Everything but the apartment may be empty. Given an email already in the
-- directory (an applicant, say), that person becomes the resident rather
-- than a second person being made. Always the caller's own company.
create or replace function public.save_resident(
  address text,
  unit text default '',
  first_name text default '',
  last_name text default '',
  email text default '',
  phone text default '',
  lease_start text default '',
  lease_end text default '',
  person_id text default null
)
returns json
language plpgsql
volatile
security definer
set search_path = public
as $fn$
declare
  caller public.people := public.lgd_caller();
  clean_address text := btrim(coalesce(address, ''));
  clean_unit text := btrim(coalesce(unit, ''));
  clean_first text := nullif(btrim(coalesce(first_name, '')), '');
  clean_last text := nullif(btrim(coalesce(last_name, '')), '');
  clean_email text := nullif(lower(btrim(coalesce(email, ''))), '');
  clean_phone text := nullif(btrim(coalesce(phone, '')), '');
  clean_start text := nullif(btrim(coalesce(lease_start, '')), '');
  clean_end text := nullif(btrim(coalesce(lease_end, '')), '');
  digits text;
  display text;
  target public.people;
  other public.people;
  place text;
begin
  if caller.id is null or not (caller.is_manager or caller.is_admin) then
    raise exception 'Only a manager or an admin can enter residents.' using errcode = '42501';
  end if;
  if caller.manager_id is null then
    raise exception 'Your login is not filed under a company.' using errcode = '22023';
  end if;
  if clean_address = '' then
    raise exception 'Pick the apartment.' using errcode = '22023';
  end if;
  if length(clean_address) > 200 or length(clean_unit) > 20 or length(coalesce(clean_first, '')) > 100
     or length(coalesce(clean_last, '')) > 100 or length(coalesce(clean_email, '')) > 254
     or length(coalesce(clean_phone, '')) > 40 then
    raise exception 'One of those is too long.' using errcode = '22023';
  end if;
  if clean_email is not null and clean_email !~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$' then
    raise exception 'That email address does not look right.' using errcode = '22023';
  end if;
  if clean_phone is not null then
    digits := regexp_replace(clean_phone, '[^0-9]', '', 'g');
    if length(digits) < 10 then
      raise exception 'The phone number needs at least 10 digits.' using errcode = '22023';
    end if;
    if length(digits) = 11 and left(digits, 1) = '1' then digits := substr(digits, 2); end if;
    if length(digits) = 10 then
      clean_phone := '(' || substr(digits, 1, 3) || ') ' || substr(digits, 4, 3) || '-' || substr(digits, 7);
    end if;
  end if;
  begin
    if clean_start is not null and (clean_start !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' or clean_start::date is null) then
      raise exception 'bad';
    end if;
    if clean_end is not null and (clean_end !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' or clean_end::date is null) then
      raise exception 'bad';
    end if;
  exception when others then
    raise exception 'A lease date does not look right.' using errcode = '22023';
  end;
  if clean_start is not null and clean_end is not null and clean_end < clean_start then
    raise exception 'The lease cannot end before it starts.' using errcode = '22023';
  end if;
  display := coalesce(nullif(btrim(coalesce(clean_first, '') || ' ' || coalesce(clean_last, '')), ''),
                      clean_email, 'Resident');

  -- Which person: the one being edited; else whoever already has the email.
  if person_id is not null then
    select * into target from public.people p where p.id = save_resident.person_id;
    if not found or not (caller.is_admin or target.manager_id is not distinct from caller.manager_id) then
      raise exception 'No such resident.' using errcode = 'P0002';
    end if;
    if clean_email is not null then
      select * into other from public.people p
       where lower(p.email) = clean_email and p.id <> target.id limit 1;
      if found then
        raise exception 'Someone else already has that email.' using errcode = '23505';
      end if;
    end if;
  elsif clean_email is not null then
    select * into target from public.people p where lower(p.email) = clean_email
     order by p.created_at limit 1;
    if found and not caller.is_admin and target.manager_id is not null
       and target.manager_id is distinct from caller.manager_id then
      raise exception 'That email belongs to someone at another company.' using errcode = '42501';
    end if;
  end if;

  place := public.lgd_property_id(coalesce(target.manager_id, caller.manager_id), clean_address, clean_unit);

  if target.id is not null then
    -- Columns qualified: this function's parameters share their names.
    update public.people p set
      is_resident = true,
      property_id = place,
      manager_id = coalesce(p.manager_id, caller.manager_id),
      first_name = case when save_resident.person_id is not null then clean_first else coalesce(clean_first, p.first_name) end,
      last_name = case when save_resident.person_id is not null then clean_last else coalesce(clean_last, p.last_name) end,
      full_name = case
        when save_resident.person_id is not null or clean_first is not null or clean_last is not null then display
        else p.full_name end,
      email = case when save_resident.person_id is not null then clean_email else coalesce(p.email, clean_email) end,
      phone = case when save_resident.person_id is not null then clean_phone else coalesce(clean_phone, p.phone) end,
      lease_start = clean_start,
      lease_end = clean_end
    where p.id = target.id
    returning p.* into target;
  else
    insert into public.people
      (id, full_name, first_name, last_name, email, phone, property_id, manager_id,
       is_resident, lease_start, lease_end, created_at)
    values (public.lgd_new_id(), display, clean_first, clean_last, clean_email, clean_phone, place,
            caller.manager_id, true, clean_start, clean_end, public.lgd_now_text())
    returning * into target;
  end if;

  return json_build_object('id', target.id, 'full_name', target.full_name,
                           'address', clean_address, 'unit', clean_unit);
end
$fn$;
revoke all on function public.save_resident(text, text, text, text, text, text, text, text, text) from public, anon;
grant execute on function public.save_resident(text, text, text, text, text, text, text, text, text) to authenticated;


-- ---------------------------------------------------------------------------
-- remove_resident - takes them out of their apartment
-- ---------------------------------------------------------------------------
--
-- The person stays in the directory (they may be an applicant, have a
-- login, or come back): they just stop being a resident of that apartment.
create or replace function public.remove_resident(person_id text)
returns json
language plpgsql
volatile
security definer
set search_path = public
as $fn$
declare
  caller public.people := public.lgd_caller();
  target public.people;
begin
  if caller.id is null or not (caller.is_manager or caller.is_admin) then
    raise exception 'Only a manager or an admin can enter residents.' using errcode = '42501';
  end if;
  select * into target from public.people p where p.id = remove_resident.person_id and p.is_resident;
  if not found or not (caller.is_admin or target.manager_id is not distinct from caller.manager_id) then
    raise exception 'No such resident.' using errcode = 'P0002';
  end if;
  update public.people p set is_resident = false, property_id = null, lease_start = null, lease_end = null
   where p.id = target.id;
  return json_build_object('id', target.id, 'full_name', target.full_name);
end
$fn$;
revoke all on function public.remove_resident(text) from public, anon;
grant execute on function public.remove_resident(text) to authenticated;

notify pgrst, 'reload schema';
