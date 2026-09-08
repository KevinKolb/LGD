-- ---------------------------------------------------------------------------
-- 001  Managers, Supabase Auth logins, users <-> people, row level security
-- ---------------------------------------------------------------------------
--
-- Run with:  python supabase/apply_migrations.py
--
-- Four things happen here, and they depend on each other in this order:
--
--   0. Renames and removals:
--        `landlords` -> `managers`, and every `landlord_id` ->
--        `manager_id`. The word meant two different things - the role a
--        person holds, and the business a lease is issued under - and only
--        the first was renamed when roles became manager/resident. This
--        finishes it.
--
--        `users` -> `webusers`. Supabase already has a `users` table:
--        `auth.users`, where GoTrue keeps identities. Two tables one schema
--        apart with the same name is a trap every query has to step around,
--        and this one is joined to that one. `webusers` says which is which.
--        NOTHING here renames `auth.users` - that table belongs to Supabase.
--
--        `notices` is dropped. The feature it backed is gone.
--
--   1. `webusers` gains `person_id`, and every login now has exactly one row in
--      `people`. A BEFORE INSERT trigger creates that row, so the rule holds
--      no matter who does the inserting - the browser signup path, the
--      `app.accounts` CLI, or a hand-written INSERT in the SQL editor.
--      `people` rows without a login stay perfectly legal: an applicant who
--      filled in the form, a resident who has never logged in. People is the
--      superset; webusers is the subset of people who can sign in.
--
--   2. `webusers` gains `auth_id`, pointing at Supabase Auth's own `auth.users`.
--      That is what actually checks a password now - this app's PBKDF2
--      `password_hash` column stays only for the FastAPI HTTP Basic path,
--      which is not what the live GitHub Pages site uses. A trigger on
--      `auth.users` creates (or adopts) the matching `public.webusers` row when
--      an email is confirmed.
--
--   3. Row level security goes on, for every table. This is not optional
--      housekeeping: the browser holds a publishable API key, and without
--      this that key can read `applications` - names, emails and phone
--      numbers of everyone who ever applied. RLS off plus Supabase's default
--      grants means "world readable to anyone holding a key that is designed
--      to be public".
--
-- WHY THE RENAME LIVES IN THIS FILE rather than a 002: the trigger functions
-- below are written in terms of column names. A later migration that renamed
-- those columns would be undone the next time this file ran, since these are
-- CREATE OR REPLACE. One file defining the final shape cannot drift from
-- itself. Everything here is idempotent and runs correctly from either
-- starting point - a database still using the old names, or one already
-- renamed - so re-running the whole set stays the normal thing to do.
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
-- 1. Columns
-- ---------------------------------------------------------------------------

-- Which manager a person belongs to. Nullable: someone who has just signed
-- up has not been placed with a manager yet, and an admin belongs to none.
alter table public.people
  add column if not exists manager_id text references public.managers(id);
create index if not exists people_manager on public.people (manager_id);

-- The Supabase Auth identity behind this login. NULL means an account that
-- predates Supabase Auth (or one only the FastAPI HTTP Basic path can use).
-- ON DELETE SET NULL rather than CASCADE: deleting an auth identity should
-- unlink the profile, never silently delete the person's directory record.
alter table public.webusers
  add column if not exists auth_id uuid references auth.users(id) on delete set null;
create unique index if not exists webusers_auth_id on public.webusers (auth_id);

-- The directory row this login belongs to. Made NOT NULL further down, once
-- the backfill and the trigger below guarantee it can always be filled.
alter table public.webusers
  add column if not exists person_id text references public.people(id);


-- ---------------------------------------------------------------------------
-- 2. Every user has a person
-- ---------------------------------------------------------------------------

create or replace function public.webwebusers_create_person()
returns trigger
language plpgsql
security definer
set search_path = public
as $fn$
begin
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

-- Both names: a trigger survives ALTER TABLE ... RENAME, so the one created
-- when this table was called `users` is still attached and would fire
-- alongside the new one - giving every new login two person rows.
drop trigger if exists users_create_person on public.webusers;
drop trigger if exists webusers_create_person on public.webusers;
create trigger webusers_create_person
  before insert on public.webusers
  for each row execute function public.webwebusers_create_person();

-- Backfill the logins that existed before this migration. Row by row rather
-- than one INSERT ... SELECT, because each new person's generated id has to
-- go back onto its own user row.
do $mig$
declare
  u record;
  new_person_id text;
begin
  for u in select * from public.webusers where person_id is null loop
    insert into public.people (id, role, full_name, email, manager_id, created_at)
    values (
      public.lgd_new_id(),
      u.role,
      coalesce(nullif(u.display_name, ''), u.username),
      u.email,
      u.manager_id,
      public.lgd_now_text()
    )
    returning id into new_person_id;
    update public.webusers set person_id = new_person_id where username = u.username;
  end loop;
end
$mig$;

alter table public.webusers alter column person_id set not null;


-- ---------------------------------------------------------------------------
-- 3. Supabase Auth signups become users (and therefore people)
-- ---------------------------------------------------------------------------
--
-- Fires on email *confirmation*, not on signup, and that timing is the whole
-- security of the adoption branch below: claiming an existing account has to
-- mean proving you can read that inbox. Keep "Confirm email" ON in the
-- project's Auth settings - with it off, Supabase stamps email_confirmed_at
-- at insert time and anyone could type a manager's address to inherit their
-- role.
--
-- New signups land as `applicant`: a real login, with no access to the
-- manager or admin areas, that an admin can promote later. This is why
-- app/config.py has to accept `applicant` as a role - a role it rejects is a
-- role that takes the whole app down at startup the moment somebody signs up
-- (see the users.email incident in app/config.py).
create or replace function public.handle_auth_user_confirmed()
returns trigger
language plpgsql
security definer
set search_path = public
as $fn$
declare
  claimed public.webusers;
begin
  -- Already linked (a re-confirmation, or an email change).
  perform 1 from public.webusers where auth_id = new.id;
  if found then
    return new;
  end if;

  -- An account created before Supabase Auth existed, whose email this person
  -- has just proved they own: adopt it, keeping its role and manager.
  select * into claimed
    from public.webusers
   where lower(email) = lower(new.email)
     and auth_id is null
   limit 1;

  if found then
    update public.webusers set auth_id = new.id where username = claimed.username;
    return new;
  end if;

  insert into public.webusers
    (username, display_name, role, manager_id, password_hash, email, auth_id)
  values (
    new.email,
    coalesce(nullif(new.raw_user_meta_data ->> 'full_name', ''), new.email),
    'applicant',
    null,
    '',                      -- no PBKDF2 hash: Supabase Auth holds the password
    new.email,
    new.id
  );
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
-- revoked; only what a signed-in person genuinely needs is handed back.
-- Right now that is exactly two reads - their own login row and their own
-- directory row - plus editing their own name and phone. Everything else
-- (applications, notices, news, properties, managers, other people) stays
-- server-side.
--
-- The loop covers every table in `public` rather than a list written out by
-- hand. A list is one more thing to remember: add a table to app/db.py,
-- forget to add it here, and it is readable by anyone who opens the site and
-- looks. Iterating means a new table is denied by default and has to be
-- opened deliberately, which is the right way round.
--
-- Note what is NOT granted: no policy lets a browser change `role` or
-- `manager_id`. Those are the fields that decide what a person can see, so
-- they are only writable by the triggers above (SECURITY DEFINER, which
-- bypasses RLS) and by the app's own postgres connection.

-- Who is asking, resolved once. SECURITY DEFINER so that reading `webusers`
-- inside another table's policy does not itself have to pass `webusers`' policy.
create or replace function public.current_person_id()
returns text
language sql
stable
security definer
set search_path = public
as $fn$
  select person_id from public.webusers where auth_id = auth.uid()
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

grant select on public.webusers to authenticated;
-- Same for policies, and for the same reason.
drop policy if exists users_select_self on public.webusers;
drop policy if exists webusers_select_self on public.webusers;
create policy webusers_select_self on public.webusers
  for select to authenticated
  using (auth_id = auth.uid());

grant select on public.people to authenticated;
grant update (full_name, phone) on public.people to authenticated;

drop policy if exists people_select_self on public.people;
create policy people_select_self on public.people
  for select to authenticated
  using (id = public.current_person_id());

drop policy if exists people_update_self on public.people;
create policy people_update_self on public.people
  for update to authenticated
  using (id = public.current_person_id())
  with check (id = public.current_person_id());

grant execute on function public.current_person_id() to authenticated;

-- PostgREST caches the schema; without this the new columns and policies are
-- invisible to the API until the next restart.
notify pgrst, 'reload schema';
