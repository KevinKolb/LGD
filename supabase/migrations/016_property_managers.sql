-- ---------------------------------------------------------------------------
-- 016  A resident sees their property managers, from people
-- ---------------------------------------------------------------------------
--
-- Run with:  python supabase/apply_migrations.py   (after 001-015), or paste
-- this whole file into the Supabase SQL editor. Idempotent.
--
-- The user, 2026-10-03, of the resident page's Your Property Manager block:
-- "pull the property manager information from the table of their property
-- manager. may be multiple." get_my_company() (014) now also lists the
-- company's managers - every person with is_manager who works for it
-- (people.clients, 012) - with their name, phone and email, so a signed-in
-- resident can reach each of them. Archived people are left out.

create or replace function public.get_my_company()
returns json
language plpgsql
stable
security definer
set search_path = public
as $fn$
declare
  caller public.people := public.lgd_caller();
  company public.managers;
  team json;
begin
  if caller.id is null then
    raise exception 'Sign in first.' using errcode = '42501';
  end if;
  select * into company from public.managers m where m.id = caller.manager_id;
  if company.id is null then
    return null;
  end if;
  select coalesce(json_agg(json_build_object(
           'name', coalesce(nullif(btrim(coalesce(p.first_name, '') || ' ' || coalesce(p.last_name, '')), ''),
                            p.full_name),
           'phone', coalesce(p.phone, ''), 'email', coalesce(p.email, ''))
           order by p.last_name, p.first_name, p.full_name), '[]'::json)
    into team
    from public.people p
   where p.is_manager
     and p.archived_at is null
     and company.id = any (p.clients);
  return json_build_object(
    'id', company.id, 'name', company.name,
    'contact_name', coalesce(company.contact_name, ''),
    'phone', coalesce(company.phone, ''), 'phone_note', coalesce(company.phone_note, ''),
    'email', coalesce(company.email, ''), 'website', coalesce(company.website, ''),
    'address', coalesce(company.address, ''),
    'managers', team);
end
$fn$;
revoke all on function public.get_my_company() from public, anon;
grant execute on function public.get_my_company() to authenticated;

notify pgrst, 'reload schema';
