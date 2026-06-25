-- ============================================================================
-- K-GPT · Migration 010 — student classification (cohort)
-- Adds year / semester / section to app_users so students can be grouped and
-- filtered by their academic cohort. Idempotent; safe to re-run.
-- ============================================================================

alter table app_users add column if not exists year     smallint;   -- 1..5
alter table app_users add column if not exists semester smallint;   -- 1..10
alter table app_users add column if not exists section  text;       -- 'A', 'B', ...

-- Helpful for admin filtering / cohort analytics.
create index if not exists idx_app_users_cohort on app_users (year, semester, section);
