-- ---------------------------------------------------------------------------
-- 018  Where mail to residentialguide.app is forwarded
-- ---------------------------------------------------------------------------
--
-- Run with:  python supabase/apply_migrations.py   (after 001-017), or paste
-- this whole file into the Supabase SQL editor. Idempotent.
--
-- The user, 2026-10-03: "setup manager@residentialguide.app and a catch all
-- on cloudflare to forward to an email address specified on the admin tab."
-- Cloudflare Email Routing sends manager@ and every other address at the
-- domain to an Email Worker (cloudflare/email-worker.js), which asks
-- mail_forward_target() where to send it. The address is one for the whole
-- site - the domain is the site's, not a company's - kept in 005's
-- site_settings as 'mail_forward'.

create or replace function public.get_mail_forward()
returns json
language plpgsql
stable
security definer
set search_path = public
as $fn$
declare
  caller public.people := public.lgd_caller();
begin
  if caller.id is null or not (caller.is_manager or caller.is_admin) then
    raise exception 'Only a manager can see where mail is forwarded.' using errcode = '42501';
  end if;
  return json_build_object('address',
    coalesce((select value from public.site_settings where key = 'mail_forward'), ''));
end
$fn$;
revoke all on function public.get_mail_forward() from public, anon;
grant execute on function public.get_mail_forward() to authenticated;

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
  if clean = '' then
    delete from public.site_settings where key = 'mail_forward';
    return public.get_mail_forward();
  end if;
  if length(clean) > 254 or clean !~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$' then
    raise exception 'That email address does not look right.' using errcode = '22023';
  end if;
  if clean like '%@residentialguide.app' then
    raise exception 'Forward to an address outside residentialguide.app, or the mail would go round in a circle.'
      using errcode = '22023';
  end if;
  insert into public.site_settings (key, value, updated_at, updated_by)
  values ('mail_forward', clean, public.lgd_now_text(), caller.id)
  on conflict (key) do update
    set value = excluded.value, updated_at = excluded.updated_at, updated_by = excluded.updated_by;
  return public.get_mail_forward();
end
$fn$;
revoke all on function public.set_mail_forward(text) from public, anon;
grant execute on function public.set_mail_forward(text) to authenticated;

-- For the Email Worker only: it calls with the project's secret key (the
-- service_role), kept as a Worker secret, never in a page.
create or replace function public.mail_forward_target()
returns text
language sql
stable
security definer
set search_path = public
as $fn$
  select value from public.site_settings where key = 'mail_forward'
$fn$;
revoke all on function public.mail_forward_target() from public, anon, authenticated;
grant execute on function public.mail_forward_target() to service_role;

notify pgrst, 'reload schema';
