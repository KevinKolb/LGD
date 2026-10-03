-- ---------------------------------------------------------------------------
-- 017  LGD's name: "LGD (Lower Garden District) Properties, Inc."
-- ---------------------------------------------------------------------------
--
-- Run with:  python supabase/apply_migrations.py   (after 001-016), or paste
-- this whole file into the Supabase SQL editor. Idempotent.
--
-- The user, 2026-10-03: change "LGD (Lower Garden District Properties),
-- Inc." to "LGD (Lower Garden District) Properties, Inc." everywhere. 008 and
-- 014 now write the new name too; this is for a database they already ran on.

update public.managers set name = 'LGD (Lower Garden District) Properties, Inc.' where id = 'lgd';
