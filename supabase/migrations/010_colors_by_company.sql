-- ---------------------------------------------------------------------------
-- 010  Each company's own two colors
-- ---------------------------------------------------------------------------
--
-- Run with:  python supabase/apply_migrations.py   (after 001-009; the
-- script applies every file in name order). Idempotent, like the others.
--
-- The user, 2026-10-02: "separate colors by company, settings only apply
-- to current company". 005 kept one pair of colors for the whole site in
-- site_settings; now each client (a row of `managers`) has its own, and a
-- signed-in page shows the colors of the client its login is working in
-- (people.manager_id, migration 008). Signed out, every page is gray
-- anyway (shared/theme.js), so there is nothing to show.

alter table public.managers add column if not exists accent text;
alter table public.managers add column if not exists accent2 text;

-- The site-wide pair saved so far was chosen at LGD: it becomes LGD's.
update public.managers m
   set accent = (select value from public.site_settings where key = 'accent'),
       accent2 = (select value from public.site_settings where key = 'accent2')
 where m.id = 'lgd' and m.accent is null and m.accent2 is null
   and exists (select 1 from public.site_settings where key = 'accent');
delete from public.site_settings where key in ('accent', 'accent2');


-- ---------------------------------------------------------------------------
-- get_site_colors - the caller's current client's colors
-- ---------------------------------------------------------------------------
--
-- Still callable signed out, as before, but then there is no client and so
-- no colors: both null, and each page keeps its own.
create or replace function public.get_site_colors()
returns json
language plpgsql
stable
security definer
set search_path = public
as $fn$
declare
  caller public.people := public.lgd_caller();
  chosen public.managers;
begin
  if caller.id is not null and caller.manager_id is not null then
    select * into chosen from public.managers m where m.id = caller.manager_id;
  end if;
  return json_build_object('accent', chosen.accent, 'accent2', chosen.accent2);
end
$fn$;
revoke all on function public.get_site_colors() from public;
grant execute on function public.get_site_colors() to anon, authenticated;


-- ---------------------------------------------------------------------------
-- set_site_colors - a manager, for the client they are working in
-- ---------------------------------------------------------------------------
--
-- Each is a "#rrggbb" color. Both empty (or null) goes back to each page's
-- own colors, Tulane green and blue - for this client only.
create or replace function public.set_site_colors(accent text, accent2 text)
returns json
language plpgsql
volatile
security definer
set search_path = public
as $fn$
declare
  caller public.people := public.lgd_caller();
  clean_accent text := lower(btrim(coalesce(accent, '')));
  clean_accent2 text := lower(btrim(coalesce(accent2, '')));
begin
  if caller.id is null or not (caller.is_manager or caller.is_admin) then
    raise exception 'Only a manager can change the colors.' using errcode = '42501';
  end if;
  if caller.manager_id is null then
    raise exception 'Your login is not filed under a company.' using errcode = '22023';
  end if;
  if clean_accent = '' and clean_accent2 = '' then
    update public.managers m set accent = null, accent2 = null where m.id = caller.manager_id;
    return public.get_site_colors();
  end if;
  if clean_accent !~ '^#[0-9a-f]{6}$' or clean_accent2 !~ '^#[0-9a-f]{6}$' then
    raise exception 'Each color needs to look like #1f5d4c.' using errcode = '22023';
  end if;
  update public.managers m set accent = clean_accent, accent2 = clean_accent2
   where m.id = caller.manager_id;
  return public.get_site_colors();
end
$fn$;
revoke all on function public.set_site_colors(text, text) from public, anon;
grant execute on function public.set_site_colors(text, text) to authenticated;

notify pgrst, 'reload schema';
