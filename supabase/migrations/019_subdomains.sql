-- ---------------------------------------------------------------------------
-- 019  Each company's own web address: <subdomain>.residentialguide.app
-- ---------------------------------------------------------------------------
--
-- Run with:  python supabase/apply_migrations.py   (after 001-018), or paste
-- this whole file into the Supabase SQL editor. Idempotent.
--
-- The user, 2026-10-03: "that's a ridiculous email address because there
-- will be multiple clients. on admin page we need to pick a unique url
-- stem. https://lgd.residentialguide.app will be for LGD, on admin page is
-- where you can pick a url subdomain."
--
-- managers.subdomain is each company's stem, unique. The site answers at
-- every <subdomain>.residentialguide.app (a Cloudflare Worker,
-- cloudflare/subdomain-worker.js, serves the same pages there), and a page
-- works out its company from the address with client_by_subdomain().
--
-- Mail follows: anything@<subdomain>.residentialguide.app goes to that
-- company's own forwarding address, managers.mail_forward - replacing 018's
-- single address for the whole site, which this hands to LGD.

alter table public.managers add column if not exists subdomain text;
alter table public.managers add column if not exists mail_forward text;
create unique index if not exists managers_subdomain on public.managers (subdomain);

update public.managers set subdomain = 'lgd' where id = 'lgd' and subdomain is null;

-- 018's one address becomes LGD's, once.
update public.managers m set mail_forward = s.value
  from public.site_settings s
 where s.key = 'mail_forward' and m.id = 'lgd' and m.mail_forward is null;
delete from public.site_settings where key = 'mail_forward';

-- A stem: lowercase letters, digits and inner hyphens, 2 to 30 long, and
-- not one the site keeps for itself.
create or replace function public.lgd_check_subdomain(value text)
returns text
language plpgsql
immutable
as $fn$
declare
  clean text := lower(btrim(coalesce(value, '')));
begin
  if clean !~ '^[a-z0-9]([a-z0-9-]{0,28}[a-z0-9])?$' or length(clean) < 2 then
    raise exception 'Use 2 to 30 letters, numbers or hyphens, starting and ending with a letter or number.'
      using errcode = '22023';
  end if;
  if clean in ('www', 'app', 'api', 'mail', 'email', 'admin', 'manager', 'managers', 'resident',
               'residents', 'applicant', 'login', 'help', 'support', 'status', 'static', 'assets',
               'dev', 'test', 'staging', 'demo') then
    raise exception 'That one is kept for the site itself. Choose another.' using errcode = '22023';
  end if;
  return clean;
end
$fn$;


-- ---------------------------------------------------------------------------
-- client_by_subdomain(subdomain) - anyone: which company an address is
-- ---------------------------------------------------------------------------
-- Answers signed out, since a page shows its company's name before anyone
-- signs in. Says only the id and the name.
create or replace function public.client_by_subdomain(subdomain text)
returns json
language sql
stable
security definer
set search_path = public
as $fn$
  select json_build_object('id', m.id, 'name', m.name)
    from public.managers m
   where m.subdomain = lower(btrim(coalesce(client_by_subdomain.subdomain, '')))
$fn$;
revoke all on function public.client_by_subdomain(text) from public;
grant execute on function public.client_by_subdomain(text) to anon, authenticated;


-- ---------------------------------------------------------------------------
-- get_my_web_settings() / set_subdomain(subdomain) / set_mail_forward(address)
-- ---------------------------------------------------------------------------
-- A manager, for the company they are working in now.
create or replace function public.get_my_web_settings()
returns json
language plpgsql
stable
security definer
set search_path = public
as $fn$
declare
  caller public.people := public.lgd_caller();
  company public.managers;
begin
  if caller.id is null or not (caller.is_manager or caller.is_admin) then
    raise exception 'Only a manager can see these settings.' using errcode = '42501';
  end if;
  select * into company from public.managers m where m.id = caller.manager_id;
  if company.id is null then
    raise exception 'Your login is not filed under a company.' using errcode = '22023';
  end if;
  return json_build_object('company', company.name,
                           'subdomain', coalesce(company.subdomain, ''),
                           'mail_forward', coalesce(company.mail_forward, ''));
end
$fn$;
revoke all on function public.get_my_web_settings() from public, anon;
grant execute on function public.get_my_web_settings() to authenticated;

create or replace function public.set_subdomain(subdomain text)
returns json
language plpgsql
volatile
security definer
set search_path = public
as $fn$
declare
  caller public.people := public.lgd_caller();
  clean text;
begin
  if caller.id is null or not (caller.is_manager or caller.is_admin) then
    raise exception 'Only a manager can change the web address.' using errcode = '42501';
  end if;
  if caller.manager_id is null then
    raise exception 'Your login is not filed under a company.' using errcode = '22023';
  end if;
  clean := public.lgd_check_subdomain(subdomain);
  if exists (select 1 from public.managers m where m.subdomain = clean and m.id <> caller.manager_id) then
    raise exception 'Another company already has that address. Choose another.' using errcode = '23505';
  end if;
  update public.managers m set subdomain = clean where m.id = caller.manager_id;
  return public.get_my_web_settings();
end
$fn$;
revoke all on function public.set_subdomain(text) from public, anon;
grant execute on function public.set_subdomain(text) to authenticated;

drop function if exists public.get_mail_forward();
create or replace function public.set_mail_forward(address text)
returns json
language plpgsql
volatile
security definer
set search_path = public
as $fn$
declare
  caller public.people := public.lgd_caller();
  clean text := lower(btrim(coalesce(address, '')));
begin
  if caller.id is null or not (caller.is_manager or caller.is_admin) then
    raise exception 'Only a manager can change where mail is forwarded.' using errcode = '42501';
  end if;
  if caller.manager_id is null then
    raise exception 'Your login is not filed under a company.' using errcode = '22023';
  end if;
  if clean <> '' and (length(clean) > 254 or clean !~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$') then
    raise exception 'That email address does not look right.' using errcode = '22023';
  end if;
  if clean like '%residentialguide.app' then
    raise exception 'Forward to an address outside residentialguide.app, or the mail would go round in a circle.'
      using errcode = '22023';
  end if;
  update public.managers m set mail_forward = nullif(clean, '') where m.id = caller.manager_id;
  return public.get_my_web_settings();
end
$fn$;
revoke all on function public.set_mail_forward(text) from public, anon;
grant execute on function public.set_mail_forward(text) to authenticated;


-- ---------------------------------------------------------------------------
-- mail_forward_target(recipient) - the Email Worker only
-- ---------------------------------------------------------------------------
-- "manager@lgd.residentialguide.app" -> LGD's forwarding address. Called
-- with the project's secret key (service_role), never from a page.
drop function if exists public.mail_forward_target();
create or replace function public.mail_forward_target(recipient text)
returns text
language sql
stable
security definer
set search_path = public
as $fn$
  select m.mail_forward
    from public.managers m
   where m.subdomain = substring(lower(btrim(coalesce(recipient, '')))
                                 from '@([a-z0-9-]+)\.residentialguide\.app$')
$fn$;
revoke all on function public.mail_forward_target(text) from public, anon, authenticated;
grant execute on function public.mail_forward_target(text) to service_role;

notify pgrst, 'reload schema';
