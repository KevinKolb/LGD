-- ---------------------------------------------------------------------------
-- 001  Managers, people (everyone, and their logins), row level security
-- ---------------------------------------------------------------------------
--
-- Run with:  python supabase/apply_migrations.py
--
-- This file defines the final shape of who is who, and is written to reach
-- it from any starting point - a database from before any of this, the
-- shape it had until 2026-09-29 (a separate `webusers` login table), or one
-- already in the final shape. Re-running it is always safe, and is the
-- normal way to bring a drifted database back into line.
--
-- THE SHAPE (settled by the user on 2026-09-29: "User can be applicant and
-- resident. Separate columns in user database. Can be manager and admin
-- too. All one table."):
--
--   `people` is the one table of everyone - applicants, residents, managers,
--   admins. A person can hold any mix of those at once, as four yes/no
--   columns: is_applicant, is_resident, is_manager, is_admin. There is no
--   single `role` any more.
--
--   A person who can sign in carries their login on the same row:
--   `username`, `password_hash` (this app's own HTTP Basic path), and
--   `auth_id` (the Supabase Auth identity the live website uses). Someone
--   who cannot sign in simply has those empty - an applicant a manager
--   added, a resident who has never logged in.
--
-- It used to be two tables, `people` and `webusers`, with every login
-- pointing at its person. Section 2 folds `webusers` into `people` and drops
-- it; everything that read `webusers` (the triggers, the row level security,
-- app/config.py, shared/auth.js) reads `people` now.
--
-- The app's own connection (the `postgres` role) has BYPASSRLS, so none of
-- the policies below change anything about how app/db.py or app/config.py
-- read and write. They only constrain the anon/authenticated roles that
-- PostgREST uses on behalf of a browser.


-- ---------------------------------------------------------------------------
-- 0. landlords -> managers
-- ---------------------------------------------------------------------------

do $rename$
declare
  target record;
begin
  if to_regclass('public.landlords') is not null
     and to_regclass('public.managers') is null then
    alter table public.landlords rename to managers;
  end if;

  -- The company's own name. The column is literally called `company` in
  -- databases created before this ran - a sensible name on a table called
  -- landlords, and a useless one on a table called managers.
  if to_regclass('public.managers') is not null
     and exists (select 1 from information_schema.columns
                  where table_schema = 'public' and table_name = 'managers'
                    and column_name = 'company')
     and not exists (select 1 from information_schema.columns
                      where table_schema = 'public' and table_name = 'managers'
                        and column_name = 'name') then
    alter table public.managers rename column company to name;
  end if;

  for target in
    select table_name from information_schema.columns
     where table_schema = 'public' and column_name = 'landlord_id'
  loop
    -- Only when the new name is not already there, so a half-renamed
    -- database cannot end up with both.
    if not exists (select 1 from information_schema.columns
                    where table_schema = 'public'
                      and table_name = target.table_name
                      and column_name = 'manager_id') then
      execute format('alter table public.%I rename column landlord_id to manager_id',
                     target.table_name);
    end if;
  end loop;
end
$rename$;

alter index if exists properties_landlord rename to properties_manager;
alter index if exists people_landlord rename to people_manager;
alter index if exists news_landlord rename to news_manager;

-- public.users -> public.webusers. Qualified every time, because the
-- unqualified name can resolve to Supabase's auth.users depending on
-- search_path, and that table is not ours to rename.
do $webusers$
begin
  if to_regclass('public.users') is not null
     and to_regclass('public.webusers') is null then
    alter table public.users rename to webusers;
  end if;
end
$webusers$;

alter index if exists users_auth_id rename to webusers_auth_id;

-- The notices feature is gone: a manager wrote a free-form message to one
-- resident, and the resident page showed it. Dropped rather than left
-- sitting there, so nothing reads or writes a table nobody maintains.
drop table if exists public.notices;


-- ---------------------------------------------------------------------------
-- Timestamps and ids, matching what Python writes
-- ---------------------------------------------------------------------------
-- created_at is TEXT on every table here, holding the ISO-8601 string
-- app/db.py's _now() produces. Anything inserted by a trigger has to match
-- that format exactly, or "ORDER BY created_at DESC" starts sorting rows
-- written by SQL differently from rows written by Python.
create or replace function public.lgd_now_text()
returns text
language sql
stable
as $fn$
  select to_char(now() at time zone 'utc', 'YYYY-MM-DD"T"HH24:MI:SS.US') || '+00:00'
$fn$;

-- Ids are 24 hex characters, the shape `secrets.token_hex(12)` produces in
-- app/db.py. gen_random_uuid() is core Postgres, so this needs no extension.
create or replace function public.lgd_new_id()
returns text
language sql
volatile
as $fn$
  select substr(replace(gen_random_uuid()::text, '-', ''), 1, 24)
$fn$;


-- ---------------------------------------------------------------------------
-- 1. Columns on people
-- ---------------------------------------------------------------------------

-- Which company a person belongs to. Nullable: someone who has just signed
-- up has not been placed with a manager yet, and an admin belongs to none.
alter table public.people
  add column if not exists manager_id text references public.managers(id);
create index if not exists people_manager on public.people (manager_id);

-- Names, split (the manager page asks first and last separately).
-- full_name stays, and is kept as "first last".
alter table public.people add column if not exists first_name text;
alter table public.people add column if not exists last_name text;
create index if not exists people_email_lower on public.people (lower(email));

-- The four roles, any mix of them.
alter table public.people add column if not exists is_applicant boolean not null default false;
alter table public.people add column if not exists is_resident boolean not null default false;
alter table public.people add column if not exists is_manager boolean not null default false;
alter table public.people add column if not exists is_admin boolean not null default false;

-- The login, for the people who have one.
alter table public.people add column if not exists username text;
alter table public.people add column if not exists password_hash text not null default '';
alter table public.people add column if not exists auth_id uuid;
create unique index if not exists people_username on public.people (username);
create unique index if not exists people_auth_id on public.people (auth_id);

-- Deleting an auth identity unlinks the person, never deletes them.
do $fk$
begin
  if not exists (select 1 from pg_constraint where conname = 'people_auth_id_fkey') then
    alter table public.people
      add constraint people_auth_id_fkey foreign key (auth_id)
      references auth.users(id) on delete set null;
  end if;
end
$fk$;


-- ---------------------------------------------------------------------------
-- 2. Roles become columns, and logins move onto people
-- ---------------------------------------------------------------------------
--
-- Both steps are guarded by what they read, so they do their work once and
-- are no-ops ever after.

do $merge$
declare
  u record;
  target text;
begin
  -- The old single `people.role`, read into the columns (landlord and
  -- tenant are that role's pre-rename spellings).
  if exists (select 1 from information_schema.columns
              where table_schema = 'public' and table_name = 'people'
                and column_name = 'role') then
    execute $q$
      update public.people set
        is_applicant = is_applicant or role = 'applicant',
        is_resident  = is_resident  or role in ('resident', 'tenant'),
        is_manager   = is_manager   or role in ('manager', 'landlord'),
        is_admin     = is_admin     or role = 'admin'
    $q$;
  end if;

  -- Each login onto its person. A login's own role is what it actually
  -- is - a person row it made when signing up still said 'applicant' after
  -- an admin promoted the login - so for people with a login, the login's
  -- role decides the columns outright.
  if to_regclass('public.webusers') is not null then
    -- A login table old enough not to have these yet still merges.
    alter table public.webusers add column if not exists email text;
    alter table public.webusers add column if not exists auth_id uuid;
    alter table public.webusers add column if not exists person_id text;
    for u in execute 'select * from public.webusers' loop
      target := u.person_id;
      if target is null then
        target := public.lgd_new_id();
        insert into public.people (id, full_name, email, manager_id, created_at)
        values (target, coalesce(nullif(u.display_name, ''), u.username), u.email,
                u.manager_id, public.lgd_now_text());
      end if;
      update public.people set
        username      = u.username,
        password_hash = coalesce(u.password_hash, ''),
        auth_id       = u.auth_id,
        email         = coalesce(email, u.email),
        manager_id    = coalesce(u.manager_id, manager_id),
        full_name     = coalesce(nullif(u.display_name, ''), full_name),
        is_applicant  = u.role = 'applicant',
        is_resident   = u.role in ('resident', 'tenant'),
        is_manager    = u.role in ('manager', 'landlord'),
        is_admin      = u.role = 'admin'
      where id = target;
    end loop;
    drop table public.webusers cascade;  -- its trigger and policy go with it
  end if;

  if exists (select 1 from information_schema.columns
              where table_schema = 'public' and table_name = 'people'
                and column_name = 'role') then
    drop index if exists public.people_role;
    alter table public.people drop column role;
  end if;
end
$merge$;

drop function if exists public.webwebusers_create_person() cascade;


-- ---------------------------------------------------------------------------
-- 3. A confirmed Supabase Auth signup is a person with a login
-- ---------------------------------------------------------------------------
--
-- Fires on email *confirmation*, not on signup, and that timing is the
-- whole security of the adoption branch below: claiming an existing person
-- has to mean proving you can read that inbox. Keep "Confirm email" ON in
-- the project's Auth settings - with it off, Supabase stamps
-- email_confirmed_at at insert time and anyone could type a manager's
-- address to inherit their roles.
--
-- A person already in the directory with that email and no login yet - an
-- applicant a manager added, a login made with the CLI - is *adopted*: the
-- new identity is attached to them, keeping their roles and company, so
-- nothing entered before is lost or doubled.
--
-- Anyone else gets no person at all (the user, 2026-09-29: a login is made
-- only for an email address already on file). Their Supabase identity
-- exists, but with no `people` row it reads nothing and every page treats
-- it as unconfirmed. The applicant page checks first (003's email_on_file)
-- and never signs such an address up; this is what holds when a signup is
-- sent some other way. So a new staff member is added as a person first -
-- as an applicant on the manager page, say - and signs up after.
create or replace function public.handle_auth_user_confirmed()
returns trigger
language plpgsql
security definer
set search_path = public
as $fn$
declare
  waiting public.people;
begin
  perform 1 from public.people where auth_id = new.id;
  if found then
    return new;  -- already linked (a re-confirmation, or an email change)
  end if;

  select * into waiting
    from public.people
   where lower(email) = lower(new.email) and auth_id is null
   order by (username is not null) desc, created_at
   limit 1;

  if found then
    update public.people set
      auth_id = new.id,
      username = coalesce(username,
        case when exists (select 1 from public.people where username = lower(new.email))
             then null else lower(new.email) end),
      is_applicant = is_applicant
        or not (is_applicant or is_resident or is_manager or is_admin)
    where id = waiting.id;
  end if;
  return new;
end
$fn$;

drop trigger if exists on_auth_user_confirmed on auth.users;
create trigger on_auth_user_confirmed
  after insert or update of email_confirmed_at on auth.users
  for each row
  when (new.email_confirmed_at is not null)
  execute function public.handle_auth_user_confirmed();


-- ---------------------------------------------------------------------------
-- 4. Row level security
-- ---------------------------------------------------------------------------
--
-- Default deny. Every table gets RLS enabled and every browser-facing grant
-- revoked; only what a signed-in person genuinely needs is handed back:
-- reading their own row of `people` (without its password hash), and
-- editing their own name and phone.
--
-- The loop covers every table in `public` rather than a list written out by
-- hand, so a table added later is denied by default and has to be opened
-- deliberately.
--
-- Note what is NOT granted: no policy lets a browser change a role column,
-- `manager_id` or anything about a login. Those decide what a person can
-- see, so only the functions here and in 002 (SECURITY DEFINER, each doing
-- its own checking) and the app's own postgres connection write them.

-- Who is asking, resolved once. SECURITY DEFINER so that reading `people`
-- inside a policy does not itself have to pass `people`' policy.
create or replace function public.current_person_id()
returns text
language sql
stable
security definer
set search_path = public
as $fn$
  select id from public.people where auth_id = auth.uid()
$fn$;

do $rls$
declare
  t text;
begin
  for t in
    select c.relname
      from pg_class c
      join pg_namespace n on n.oid = c.relnamespace
     where n.nspname = 'public' and c.relkind = 'r'
  loop
    execute format('alter table public.%I enable row level security', t);
    execute format('revoke all on public.%I from anon, authenticated', t);
  end loop;
end
$rls$;

-- Every column of your own row but the password hash.
grant select (id, full_name, first_name, last_name, email, phone, property_id,
              manager_id, created_at, username, auth_id,
              is_applicant, is_resident, is_manager, is_admin)
  on public.people to authenticated;
grant update (full_name, phone) on public.people to authenticated;

drop policy if exists people_select_self on public.people;
create policy people_select_self on public.people
  for select to authenticated
  using (auth_id = auth.uid());

drop policy if exists people_update_self on public.people;
create policy people_update_self on public.people
  for update to authenticated
  using (auth_id = auth.uid())
  with check (auth_id = auth.uid());

grant execute on function public.current_person_id() to authenticated;

-- PostgREST caches the schema; without this the new columns and policies are
-- invisible to the API until the next restart.
notify pgrst, 'reload schema';
