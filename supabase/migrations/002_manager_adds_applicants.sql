-- ---------------------------------------------------------------------------
-- 002  A manager adds an applicant from the manager page
-- ---------------------------------------------------------------------------
--
-- Run with:  python supabase/apply_migrations.py   (after 001, which it
-- builds on - the script applies every file in name order, so this one
-- always runs last and its CREATE OR REPLACE is the version that stands).
--
-- The user, 2026-09-29: "a feature on the manager page that allows the
-- manager to create an applicant. Fields gathered are first, last, email
-- and mobile. That will be stored for later use to fill in application
-- info and to create a login account to this portal."
--
-- Three things:
--
--   1. `people` gains `first_name` and `last_name`. `full_name` stays (NOT
--      NULL, and everything already reads it) and is kept as "first last".
--      The mobile number is the existing `phone` column.
--
--   2. Two functions the manager page calls through PostgREST
--      (/rest/v1/rpc/...): `create_applicant` and `list_applicants`. The
--      browser still has no write access to `people` at all - 001's default
--      deny stands. These run as their owner (SECURITY DEFINER) and do
--      their own checking instead, which is narrower than any policy could
--      be: the caller must be a signed-in manager or admin, the new row is
--      always role 'applicant', and its manager_id is always the caller's own
--      company - never a value the browser sent.
--
--   3. A login made later with the same email *adopts* that person rather
--      than creating a second one. That is the "create a login account"
--      half: the applicant signs up (or is invited) with the address the
--      manager typed, and on confirming it their login is linked to the
--      record the manager made - so nothing typed now is lost or doubled.
--      Adoption happens only on email confirmation (001's trigger on
--      auth.users), so claiming a record still means proving you can read
--      that inbox.


-- ---------------------------------------------------------------------------
-- 1. Columns
-- ---------------------------------------------------------------------------

alter table public.people add column if not exists first_name text;
alter table public.people add column if not exists last_name text;
create index if not exists people_email_lower on public.people (lower(email));


-- ---------------------------------------------------------------------------
-- 2. Who is calling
-- ---------------------------------------------------------------------------

-- The signed-in caller's login row, or nothing. SECURITY DEFINER so it can
-- read `webusers` past its own row-level policy.
create or replace function public.lgd_caller()
returns public.webusers
language sql
stable
security definer
set search_path = public
as $fn$
  select * from public.webusers where auth_id = auth.uid()
$fn$;
revoke all on function public.lgd_caller() from public, anon, authenticated;


-- ---------------------------------------------------------------------------
-- 3. create_applicant
-- ---------------------------------------------------------------------------

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
  caller public.webusers := public.lgd_caller();
  clean_first text := btrim(coalesce(first_name, ''));
  clean_last text := btrim(coalesce(last_name, ''));
  clean_email text := lower(btrim(coalesce(email, '')));
  clean_mobile text := btrim(coalesce(mobile, ''));
  digits text;
  created public.people;
begin
  if caller.username is null or caller.role not in ('manager', 'admin') then
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
  if length(regexp_replace(clean_mobile, '[^0-9]', '', 'g')) < 10 then
    raise exception 'The mobile number needs at least 10 digits.' using errcode = '22023';
  end if;
  -- One way of writing a US number, however it was typed: (504) 555-1234.
  -- Anything else (an international number) is kept as typed.
  digits := regexp_replace(clean_mobile, '[^0-9]', '', 'g');
  if length(digits) = 11 and left(digits, 1) = '1' then
    digits := substr(digits, 2);
  end if;
  if length(digits) = 10 then
    clean_mobile := '(' || substr(digits, 1, 3) || ') ' || substr(digits, 4, 3) || '-' || substr(digits, 7);
  end if;
  if exists (select 1 from public.people p where lower(p.email) = clean_email) then
    raise exception 'Someone with that email is already in the directory.'
      using errcode = '23505';
  end if;

  insert into public.people
    (id, role, full_name, first_name, last_name, email, phone, manager_id, created_at)
  values (
    public.lgd_new_id(), 'applicant', clean_first || ' ' || clean_last,
    clean_first, clean_last, clean_email, clean_mobile, caller.manager_id,
    public.lgd_now_text()
  )
  returning * into created;

  return json_build_object(
    'id', created.id, 'first_name', created.first_name, 'last_name', created.last_name,
    'email', created.email, 'mobile', created.phone, 'created_at', created.created_at,
    'has_login', false
  );
end
$fn$;
revoke all on function public.create_applicant(text, text, text, text) from public, anon;
grant execute on function public.create_applicant(text, text, text, text) to authenticated;


-- ---------------------------------------------------------------------------
-- 4. list_applicants
-- ---------------------------------------------------------------------------

-- The applicants a manager's company has, newest first; every company's
-- for an admin. `has_login` says whether they have signed up yet.
create or replace function public.list_applicants()
returns table (
  id text, first_name text, last_name text, email text, mobile text,
  created_at text, has_login boolean
)
language plpgsql
stable
security definer
set search_path = public
as $fn$
declare
  caller public.webusers := public.lgd_caller();
begin
  if caller.username is null or caller.role not in ('manager', 'admin') then
    raise exception 'Only a manager or an admin can see applicants.'
      using errcode = '42501';
  end if;
  return query
    select p.id, coalesce(p.first_name, p.full_name), coalesce(p.last_name, ''),
           p.email, p.phone, p.created_at,
           exists (select 1 from public.webusers w where w.person_id = p.id)
      from public.people p
     where p.role = 'applicant'
       -- A login promoted to manager or admin keeps the directory row it
       -- signed up with, still saying 'applicant'; its login says what it is.
       and not exists (select 1 from public.webusers w
                        where w.person_id = p.id and w.role <> 'applicant')
       and (caller.role = 'admin' or p.manager_id is not distinct from caller.manager_id)
     order by p.created_at desc
     limit 500;
end
$fn$;
revoke all on function public.list_applicants() from public, anon;
grant execute on function public.list_applicants() to authenticated;


-- ---------------------------------------------------------------------------
-- 5. A later login adopts the person made for it
-- ---------------------------------------------------------------------------
--
-- Replaces 001's version of this trigger function (same name, so 001's
-- CREATE TRIGGER keeps pointing at it). The only change: before creating a
-- person for a new login, look for one with the same email that no login
-- has claimed yet, and use that. The login also takes the person's company
-- when it has none of its own.
create or replace function public.webwebusers_create_person()
returns trigger
language plpgsql
security definer
set search_path = public
as $fn$
declare
  waiting public.people;
begin
  if new.person_id is null and coalesce(new.email, '') <> '' then
    select * into waiting
      from public.people p
     where lower(p.email) = lower(new.email)
       and not exists (select 1 from public.webusers w where w.person_id = p.id)
     order by p.created_at
     limit 1;
    if found then
      new.person_id := waiting.id;
      new.manager_id := coalesce(new.manager_id, waiting.manager_id);
    end if;
  end if;

  if new.person_id is null then
    insert into public.people (id, role, full_name, email, manager_id, created_at)
    values (
      public.lgd_new_id(),
      new.role,
      coalesce(nullif(new.display_name, ''), new.username),
      new.email,
      new.manager_id,
      public.lgd_now_text()
    )
    returning id into new.person_id;
  end if;
  return new;
end
$fn$;

notify pgrst, 'reload schema';
