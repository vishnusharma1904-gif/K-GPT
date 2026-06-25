-- ============================================================================
-- K-GPT · Migration 011 — course & branch for student classification
-- Completes the cohort profile: course (B.Tech / M.Tech / MBA / Diploma …) and
-- branch (CSE / ECE / MECH …). Pairs with 010 (year/semester/section).
-- Idempotent; safe to re-run.
-- ============================================================================

alter table app_users add column if not exists course text;   -- 'B.Tech', 'M.Tech', 'MBA', 'Diploma', ...
alter table app_users add column if not exists branch text;   -- 'CSE', 'ECE', 'EEE', 'MECH', 'CIVIL', ...

create index if not exists idx_app_users_course_branch on app_users (course, branch);
