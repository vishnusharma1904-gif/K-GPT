-- ============================================================================
-- K-GPT · Migration 012 — admission year (auto-progressing cohort)
-- Store the student's joining/batch year; current academic year + odd/even
-- semester are then DERIVED from the calendar, so they advance automatically
-- with time and never need a manual update. year/semester columns (010) remain
-- as an optional cache/override. Idempotent.
-- ============================================================================

alter table app_users add column if not exists admission_year smallint;  -- e.g. 2023

create index if not exists idx_app_users_admission on app_users (admission_year);
