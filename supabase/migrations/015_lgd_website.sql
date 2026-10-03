-- ---------------------------------------------------------------------------
-- 015  LGD's website is this site
-- ---------------------------------------------------------------------------
--
-- Run with:  python supabase/apply_migrations.py   (after 001-014), or paste
-- this whole file into the Supabase SQL editor. Idempotent.
--
-- The user, 2026-10-03, of the resident page's Your Property Manager block:
-- https://residentialguide.app "in place of https://neworleans.properties/".
-- 014 filled in the old address; this runs after it, so re-running the set
-- keeps the new one. The email address stays LGD@neworleans.properties.

update public.managers set website = 'https://residentialguide.app' where id = 'lgd';
