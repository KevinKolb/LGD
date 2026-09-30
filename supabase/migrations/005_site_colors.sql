-- ---------------------------------------------------------------------------
-- 005  The site's two main colors, chosen by an admin
-- ---------------------------------------------------------------------------
--
-- Run with:  python supabase/apply_migrations.py   (after 001-004; the
-- script applies every file in name order). Idempotent, like the others.
--
-- The user, 2026-09-30: a section on the admin page to change the site's
-- two main colors - the main color (--accent, Tulane green by default:
-- header bars, buttons, links) and the second color (--accent2, Tulane light
-- blue: the rule under each header, hovers, the staff buttons). Every site
-- page reads them through shared/theme.js; with none saved, each page keeps
-- the colors in its own stylesheet.

create table if not exists public.site_settings (
  key        text primary key,
  value      text not null,
  updated_at text not null,
  updated_by text
);

-- Locked like 004's table: 001's loop only covers tables that exist when
-- it runs. Read through get_site_colors, written through set_site_colors.
alter table public.site_settings enable row level security;
revoke all on public.site_settings from anon, authenticated;


-- ---------------------------------------------------------------------------
-- get_site_colors - anyone, signed in or not
-- ---------------------------------------------------------------------------
--
-- Every page shows the colors, the home page and the login page included,
-- so this answers signed out. It says only the two colors.
create or replace function public.get_site_colors()
returns json
language sql
stable
security definer
set search_path = public
as $fn$
  select json_build_object(
    'accent', (select value from public.site_settings where key = 'accent'),
    'accent2', (select value from public.site_settings where key = 'accent2')
  )
$fn$;
revoke all on function public.get_site_colors() from public;
grant execute on function public.get_site_colors() to anon, authenticated;


-- ---------------------------------------------------------------------------
-- set_site_colors - admins only
-- ---------------------------------------------------------------------------
--
-- Each is a "#rrggbb" color. Both empty (or null) goes back to each page's
-- own colors, Tulane green and blue.
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
  if caller.id is null or not caller.is_admin then
    raise exception 'Only an admin can change the site''s colors.' using errcode = '42501';
  end if;
  if clean_accent = '' and clean_accent2 = '' then
    delete from public.site_settings where key in ('accent', 'accent2');
    return public.get_site_colors();
  end if;
  if clean_accent !~ '^#[0-9a-f]{6}$' or clean_accent2 !~ '^#[0-9a-f]{6}$' then
    raise exception 'Each color needs to look like #1f5d4c.' using errcode = '22023';
  end if;
  insert into public.site_settings (key, value, updated_at, updated_by)
  values ('accent', clean_accent, public.lgd_now_text(), caller.id),
         ('accent2', clean_accent2, public.lgd_now_text(), caller.id)
  on conflict (key) do update
    set value = excluded.value, updated_at = excluded.updated_at, updated_by = excluded.updated_by;
  return public.get_site_colors();
end
$fn$;
revoke all on function public.set_site_colors(text, text) from public, anon;
grant execute on function public.set_site_colors(text, text) to authenticated;

notify pgrst, 'reload schema';
