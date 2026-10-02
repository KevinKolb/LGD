-- ---------------------------------------------------------------------------
-- 011  Unit names as they are written on paper
-- ---------------------------------------------------------------------------
--
-- Run with:  python supabase/apply_migrations.py   (after 001-010).
-- Idempotent: once renamed, the old names are no longer there to match.
--
-- The user, 2026-10-02: "change names of units to match what's on paper.
-- #2 (102) for example". documents/properties.json now names 1364 Camp's
-- units "#1 (101)" to "#7 (204)" and 1521 St. Andrew's "#1" to "#6"
-- (1558 Camp's A, B and C were already so). A unit is stored as its name,
-- so every table holding one follows.

do $$
declare
  n record;
begin
  for n in
    select * from (values
      ('1364 Camp St.', '1', '#1 (101)'), ('1364 Camp St.', '2', '#2 (102)'),
      ('1364 Camp St.', '3', '#3 (103)'), ('1364 Camp St.', '4', '#4 (201)'),
      ('1364 Camp St.', '5', '#5 (202)'), ('1364 Camp St.', '6', '#6 (203)'),
      ('1364 Camp St.', '7', '#7 (204)'),
      ('1521 St. Andrew St.', '1', '#1'), ('1521 St. Andrew St.', '2', '#2'),
      ('1521 St. Andrew St.', '3', '#3'), ('1521 St. Andrew St.', '4', '#4'),
      ('1521 St. Andrew St.', '5', '#5'), ('1521 St. Andrew St.', '6', '#6')
    ) as t(address, old_unit, new_unit)
  loop
    update public.properties pr set apt = n.new_unit
     where pr.manager_id = 'lgd' and pr.address = n.address and pr.apt = n.old_unit;
    update public.open_apartments o set unit = n.new_unit
     where o.manager_id = 'lgd' and o.address = n.address and o.unit = n.old_unit;
    update public.rent_payments r set unit = n.new_unit
     where r.manager_id = 'lgd' and r.address = n.address and r.unit = n.old_unit;
    update public.people p set apply_unit = n.new_unit
     where p.manager_id = 'lgd' and p.apply_address = n.address and p.apply_unit = n.old_unit;
  end loop;
end $$;
