-- ---------------------------------------------------------------------------
-- 014  Each company's contact information, in the company table
-- ---------------------------------------------------------------------------
--
-- Run with:  python supabase/apply_migrations.py   (after 001-013), or paste
-- this whole file into the Supabase SQL editor. Idempotent.
--
-- The user, 2026-10-02: "resident page gets separate contact info blocks
-- based on company. pull from single company table. edit company table
-- with current lgd info, all fields." The resident page's Contact block
-- was LGD's, written into the page. Now `managers` - the companies (see
-- CLAUDE.md on the name) - holds each one's contact details, and the page
-- asks for the signed-in person's own company.

alter table public.managers add column if not exists contact_name text;
alter table public.managers add column if not exists phone text;
alter table public.managers add column if not exists phone_note text;
alter table public.managers add column if not exists website text;
alter table public.managers add column if not exists address text;

-- LGD, as the resident page and the paper forms have it: Pam and Steve
-- Hartnett, the office at 1556 Camp Street (where the lease has rent paid),
-- and Steve A. Hartnett signing as Lessor/Agent (his name heads the
-- security deposit form). Orange Street has none of this yet.
update public.managers set
  name = 'LGD (Lower Garden District) Properties, Inc.',
  signer_name = 'Steve A. Hartnett',
  contact_name = 'Pam and Steve Hartnett',
  email = 'LGD@neworleans.properties',
  phone = '504.913.1556',
  phone_note = 'call or text',
  website = 'https://neworleans.properties',
  address = '1556 Camp St., New Orleans, LA 70130'
where id = 'lgd';


-- ---------------------------------------------------------------------------
-- get_my_company() - the signed-in person's company, to contact it
-- ---------------------------------------------------------------------------
-- Any signed-in person (a resident, an applicant, a manager), for the
-- company they are filed under now. Nothing for one filed under none.
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
begin
  if caller.id is null then
    raise exception 'Sign in first.' using errcode = '42501';
  end if;
  select * into company from public.managers m where m.id = caller.manager_id;
  if company.id is null then
    return null;
  end if;
  return json_build_object(
    'id', company.id, 'name', company.name,
    'contact_name', coalesce(company.contact_name, ''),
    'phone', coalesce(company.phone, ''), 'phone_note', coalesce(company.phone_note, ''),
    'email', coalesce(company.email, ''), 'website', coalesce(company.website, ''),
    'address', coalesce(company.address, ''));
end
$fn$;
revoke all on function public.get_my_company() from public, anon;
grant execute on function public.get_my_company() to authenticated;

notify pgrst, 'reload schema';
