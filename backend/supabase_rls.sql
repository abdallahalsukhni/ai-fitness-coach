-- ============================================================
-- RLS policies for workouts table
-- Run this in Supabase SQL Editor after supabase_setup.sql
-- ============================================================

-- Allow the anon key to read and write workouts
-- (This project has no auth — a single hardcoded user_id)
alter table workouts enable row level security;

create policy "Allow all operations for anon"
  on workouts
  for all
  to anon
  using (true)
  with check (true);
