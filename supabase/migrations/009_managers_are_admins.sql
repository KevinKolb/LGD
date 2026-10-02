-- ---------------------------------------------------------------------------
-- 009  One staff credential: manager
-- ---------------------------------------------------------------------------
--
-- Run with:  python supabase/apply_migrations.py   (after 001-008; the
-- script applies every file in name order). Idempotent, like the others.
--
-- The user, 2026-10-02: "let's combine manager and admin into one
-- credential. pam and kevin are managers. current admin page is accessible
-- through a gear button on manager page." So a manager can do what only an
-- admin could: open the admin page and set the site's colors. The is_admin
-- column stays (the multi-company spine, and the old checks, read it), but
-- every admin is a manager too, and nothing needs an admin alone any more.

update public.people set is_manager = true where is_admin and not is_manager;

-- 005's set_site_colors, now for any manager (an admin still passes).
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
    raise exception 'Only a manager can change the site''s colors.' using errcode = '42501';
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
