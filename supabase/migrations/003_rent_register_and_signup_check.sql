-- ---------------------------------------------------------------------------
-- 003  The rent register's residents, and the applicant page's signup check
-- ---------------------------------------------------------------------------
--
-- Run with:  python supabase/apply_migrations.py   (after 001 and 002; the
-- script applies every file in name order). Idempotent, like the others.

-- ---------------------------------------------------------------------------
-- list_residents
-- ---------------------------------------------------------------------------
--
-- The manager page's monthly rent register (the user, 2026-09-29) lists
-- every unit with its tenants, their email and phone. A resident's unit is
-- their property_id -> properties (address, apt), with the address written
-- as documents/properties.json writes it, which is how the register matches
-- them to a unit. A signed-in manager sees their own company's residents;
-- an admin sees every company's. The browser still cannot read `people`
-- itself - 001's default deny stands.
create or replace function public.list_residents()
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
    raise exception 'Only a manager or an admin can see the residents.'
      using errcode = '42501';
  end if;
  return query
    select json_build_object(
             'id', p.id, 'full_name', p.full_name, 'email', p.email, 'phone', p.phone,
             'address', pr.address, 'unit', coalesce(pr.apt, ''))
      from public.people p
      join public.properties pr on pr.id = p.property_id
     where p.is_resident
       and (caller.is_admin or p.manager_id is not distinct from caller.manager_id)
     order by pr.address, pr.apt, p.full_name;
end
$fn$;
revoke all on function public.list_residents() from public, anon;
grant execute on function public.list_residents() to authenticated;


-- ---------------------------------------------------------------------------
-- email_on_file
-- ---------------------------------------------------------------------------
--
-- The applicant page creates a login only for an email address already in
-- `people` - someone a manager added (the user, 2026-09-29: "if not, don't
-- continue user setup process and say: that email address is not yet on
-- file"). The page asks this before it signs anyone up, so it has to be
-- callable signed out.
--
-- It answers yes or no and nothing else - never a name or which company.
-- That still lets someone test whether an address is on file, which is
-- what the rule asks for; the answer is no more than the signup form
-- itself would reveal. The check that actually holds is 001's
-- handle_auth_user_confirmed, which gives a login to no one who is not
-- already on file, however the signup was sent.
create or replace function public.email_on_file(email text)
returns boolean
language sql
stable
security definer
set search_path = public
as $fn$
  select exists (
    select 1 from public.people p
     where lower(p.email) = lower(btrim(coalesce(email_on_file.email, '')))
       and btrim(coalesce(email_on_file.email, '')) <> ''
  )
$fn$;
revoke all on function public.email_on_file(text) from public;
grant execute on function public.email_on_file(text) to anon, authenticated;

notify pgrst, 'reload schema';
