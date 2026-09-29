-- ---------------------------------------------------------------------------
-- 002  Applicants on the manager page: add, list, archive
-- ---------------------------------------------------------------------------
--
-- Run with:  python supabase/apply_migrations.py   (after 001, whose final
-- shape of `people` - four role columns, logins on the same row - this is
-- written against; the script applies every file in name order).
--
-- The user, 2026-09-29: the manager page adds an applicant - first, last,
-- email and mobile - "stored for later use to fill in application info and
-- to create a login account to this portal"; picks one from the list to
-- send them the application; archives them; and can see the archived ones.
--
-- The browser still has no write access to `people` - 001's default deny
-- stands. These functions run as their owner (SECURITY DEFINER) and do
-- their own checking instead, which is narrower than any policy could be:
-- the caller must be a signed-in manager or admin; a manager only ever
-- touches their own company's people; a new applicant is always filed under
-- the caller's company - never a company the browser sends.
--
-- The login half needs nothing here: when the applicant signs up with the
-- address the manager typed and confirms it, 001's trigger attaches their
-- new login to this same row.

-- An applicant can be archived - out of the manager's list, kept in the
-- directory, and back again with one click.
alter table public.people add column if not exists archived_at text;

-- The signed-in caller's row, or nothing. SECURITY DEFINER so it can read
-- `people` past its own row-level policy.
create or replace function public.lgd_caller()
returns public.people
language sql
stable
security definer
set search_path = public
as $fn$
  select * from public.people where auth_id = auth.uid()
$fn$;
revoke all on function public.lgd_caller() from public, anon, authenticated;

-- One applicant as the manager page shows them.
create or replace function public.lgd_applicant_json(p public.people)
returns json
language sql
stable
as $fn$
  select json_build_object(
    'id', p.id,
    'first_name', coalesce(p.first_name, p.full_name),
    'last_name', coalesce(p.last_name, ''),
    'email', p.email, 'mobile', p.phone, 'created_at', p.created_at,
    'archived', p.archived_at is not null,
    'is_resident', p.is_resident,
    'has_login', p.auth_id is not null or p.password_hash <> ''
  )
$fn$;
revoke all on function public.lgd_applicant_json(public.people) from public, anon, authenticated;


-- ---------------------------------------------------------------------------
-- create_applicant
-- ---------------------------------------------------------------------------
--
-- Someone already in the directory with that email - a resident applying
-- for another apartment, say - is not a second person: they become an
-- applicant too (the user: "User can be applicant and resident"). Only an
-- applicant already on the list is refused.
create or replace function public.create_applicant(
  first_name text,
  last_name text,
  email text,
  mobile text
)
returns json
language plpgsql
volatile
security definer
set search_path = public
as $fn$
declare
  caller public.people := public.lgd_caller();
  clean_first text := btrim(coalesce(first_name, ''));
  clean_last text := btrim(coalesce(last_name, ''));
  clean_email text := lower(btrim(coalesce(email, '')));
  clean_mobile text := btrim(coalesce(mobile, ''));
  digits text;
  existing public.people;
  result public.people;
begin
  if caller.id is null or not (caller.is_manager or caller.is_admin) then
    raise exception 'Only a manager or an admin can add an applicant.'
      using errcode = '42501';
  end if;
  if clean_first = '' or clean_last = '' or clean_email = '' or clean_mobile = '' then
    raise exception 'First name, last name, email and mobile are all needed.'
      using errcode = '22023';
  end if;
  if length(clean_first) > 100 or length(clean_last) > 100
     or length(clean_email) > 254 or length(clean_mobile) > 40 then
    raise exception 'One of those is too long.' using errcode = '22023';
  end if;
  if clean_email !~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$' then
    raise exception 'That email address does not look right.' using errcode = '22023';
  end if;
  digits := regexp_replace(clean_mobile, '[^0-9]', '', 'g');
  if length(digits) < 10 then
    raise exception 'The mobile number needs at least 10 digits.' using errcode = '22023';
  end if;
  -- One way of writing a US number, however it was typed: (504) 555-1234.
  -- Anything else (an international number) is kept as typed.
  if length(digits) = 11 and left(digits, 1) = '1' then
    digits := substr(digits, 2);
  end if;
  if length(digits) = 10 then
    clean_mobile := '(' || substr(digits, 1, 3) || ') ' || substr(digits, 4, 3) || '-' || substr(digits, 7);
  end if;

  select * into existing from public.people p where lower(p.email) = clean_email
   order by p.created_at limit 1;
  if found then
    if not caller.is_admin and existing.manager_id is not null
       and existing.manager_id is distinct from caller.manager_id then
      raise exception 'That email belongs to someone at another company.'
        using errcode = '42501';
    end if;
    if existing.is_applicant and existing.archived_at is null then
      raise exception 'That person is already on the applicant list.'
        using errcode = '23505';
    end if;
    -- Columns qualified: this function's parameters share their names.
    update public.people p set
      is_applicant = true,
      archived_at = null,
      first_name = coalesce(p.first_name, clean_first),
      last_name = coalesce(p.last_name, clean_last),
      phone = coalesce(p.phone, clean_mobile),
      manager_id = coalesce(p.manager_id, caller.manager_id)
    where p.id = existing.id
    returning p.* into result;
  else
    insert into public.people
      (id, full_name, first_name, last_name, email, phone, manager_id,
       is_applicant, created_at)
    values (
      public.lgd_new_id(), clean_first || ' ' || clean_last,
      clean_first, clean_last, clean_email, clean_mobile, caller.manager_id,
      true, public.lgd_now_text()
    )
    returning * into result;
  end if;
  return public.lgd_applicant_json(result);
end
$fn$;
revoke all on function public.create_applicant(text, text, text, text) from public, anon;
grant execute on function public.create_applicant(text, text, text, text) to authenticated;


-- ---------------------------------------------------------------------------
-- list_applicants
-- ---------------------------------------------------------------------------
--
-- A company's applicants, newest first - the current ones, or the archived
-- ones when `archived` is true. Every company's for an admin.
drop function if exists public.list_applicants();
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
       and (caller.is_admin or p.manager_id is not distinct from caller.manager_id)
     order by coalesce(p.archived_at, p.created_at) desc
     limit 500;
end
$fn$;
revoke all on function public.list_applicants(boolean) from public, anon;
grant execute on function public.list_applicants(boolean) to authenticated;


-- ---------------------------------------------------------------------------
-- set_applicant_archived
-- ---------------------------------------------------------------------------
create or replace function public.set_applicant_archived(person_id text, archived boolean)
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
    raise exception 'Only a manager or an admin can archive an applicant.'
      using errcode = '42501';
  end if;
  select * into target from public.people p where p.id = person_id and p.is_applicant;
  if not found
     or (not caller.is_admin and target.manager_id is distinct from caller.manager_id) then
    raise exception 'No such applicant.' using errcode = 'P0002';
  end if;
  update public.people set
    archived_at = case when archived then public.lgd_now_text() else null end
  where id = target.id
  returning * into target;
  return public.lgd_applicant_json(target);
end
$fn$;
revoke all on function public.set_applicant_archived(text, boolean) from public, anon;
grant execute on function public.set_applicant_archived(text, boolean) to authenticated;

notify pgrst, 'reload schema';
