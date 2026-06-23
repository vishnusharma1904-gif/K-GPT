-- ============================================================================
-- K-GPT · Migration 004 — remaining phases (Epics A/D/F/H/I)
-- Adds: feature flags (P4), OAuth identities (P3), prompt library (P24),
--       study aids (P38), cohort budgets / cost governance (P46),
--       incidents/status (P47), pilot feedback + NPS (P50).
-- Idempotent; safe to run after 003.
-- ============================================================================

-- --- app_users: SSO + provider linkage (P3) --------------------------------
alter table app_users add column if not exists auth_provider text not null default 'password'; -- password | google
alter table app_users add column if not exists provider_sub  text;                              -- google "sub" claim
alter table app_users add column if not exists avatar_url     text;
alter table app_users add column if not exists cohort         text;                              -- e.g. 'CSE-2026-A' for budgets/analytics
create index if not exists idx_users_provider_sub on app_users (provider_sub) where provider_sub is not null;
create index if not exists idx_users_cohort on app_users (cohort);

-- --- Feature flags (P4) -----------------------------------------------------
create table if not exists feature_flags (
  key         text primary key,                    -- 'voice', 'code_interpreter', ...
  enabled     boolean not null default false,
  description text,
  rollout_pct int not null default 0,              -- 0-100 gradual rollout
  updated_at  timestamptz not null default now()
);
insert into feature_flags (key, enabled, description, rollout_pct) values
  ('voice',            false, 'Voice mode (STT/TTS) — P35',            0),
  ('code_interpreter', true,  'Sandboxed Python execution — P36',      100),
  ('vision',           true,  'Image understanding — P34',             100),
  ('web_search',       true,  'Web search grounding — P33',            100),
  ('artifacts',        true,  'Artifacts / Canvas split pane — P23',   100),
  ('study_aids',       true,  'Flashcards / quiz / summary — P38',     100)
on conflict (key) do nothing;

-- --- Prompt library & slash commands (P24) ----------------------------------
create table if not exists prompts (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid references app_users(id) on delete cascade,  -- null = shared starter
  slug        text not null,                       -- '/essay', '/review'
  title       text not null,
  body        text not null,
  shared      boolean not null default false,      -- starter templates seeded by admin
  created_at  timestamptz not null default now()
);
create index if not exists idx_prompts_user on prompts (user_id);
create index if not exists idx_prompts_shared on prompts (shared) where shared = true;
-- seed starter templates (user_id null + shared)
insert into prompts (id, user_id, slug, title, body, shared) values
  (gen_random_uuid(), null, '/essay',   'Essay outline',
   'Write a clear, well-structured outline for an essay on: {topic}. Include a thesis, 3 supporting points, and a conclusion.', true),
  (gen_random_uuid(), null, '/explain', 'Explain simply',
   'Explain the following concept in simple terms with one everyday analogy: {concept}', true),
  (gen_random_uuid(), null, '/review',  'Code review',
   'Review this code for correctness, readability, and bugs. Suggest concrete improvements:\n\n{code}', true),
  (gen_random_uuid(), null, '/quiz',    'Make a quiz',
   'Create a 5-question multiple-choice quiz (with answers) to test understanding of: {topic}', true),
  (gen_random_uuid(), null, '/summarize','Summarize',
   'Summarize the following into 5 concise bullet points a student can revise from:\n\n{text}', true)
on conflict do nothing;

-- --- Study aids (P38) -------------------------------------------------------
create table if not exists study_aids (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references app_users(id) on delete cascade,
  session_id  uuid references chat_sessions(id) on delete set null,
  kind        text not null,                       -- 'flashcards' | 'quiz' | 'summary'
  title       text,
  payload     jsonb not null,                      -- structured cards/questions
  created_at  timestamptz not null default now()
);
create index if not exists idx_studyaids_user on study_aids (user_id, created_at desc);

-- --- Cost governance: per-cohort budgets (P46) ------------------------------
create table if not exists cohort_budgets (
  cohort        text primary key,                  -- matches app_users.cohort
  monthly_usd   numeric(10,2) not null default 0,  -- spend cap in USD
  alert_pct     int not null default 80,           -- alert threshold
  throttled     boolean not null default false,    -- auto-set on breach
  updated_at    timestamptz not null default now()
);

-- --- Reliability: incidents / status (P47) ----------------------------------
create table if not exists incidents (
  id          uuid primary key default gen_random_uuid(),
  title       text not null,
  severity    text not null default 'minor',       -- minor | major | critical
  status      text not null default 'investigating', -- investigating | identified | monitoring | resolved
  body        text,
  created_at  timestamptz not null default now(),
  resolved_at timestamptz
);
create index if not exists idx_incidents_open on incidents (status) where status <> 'resolved';

-- --- Pilot feedback + NPS (P50) ---------------------------------------------
create table if not exists feedback_responses (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references app_users(id) on delete cascade,
  kind        text not null default 'nps',         -- 'nps' | 'csat' | 'free'
  score       int,                                 -- NPS 0-10 / CSAT 1-5
  comment     text,
  context     text,                                -- where it was collected
  created_at  timestamptz not null default now()
);
create index if not exists idx_feedback_user on feedback_responses (user_id);
create index if not exists idx_feedback_kind on feedback_responses (kind, created_at desc);

-- --- RLS on new per-user tables ---------------------------------------------
alter table prompts            enable row level security;
alter table study_aids         enable row level security;
alter table feedback_responses enable row level security;

do $$ begin
  create policy own_prompts on prompts using (user_id is null or user_id::text = auth.uid()::text);
exception when duplicate_object then null; end $$;
do $$ begin
  create policy own_studyaids on study_aids using (user_id::text = auth.uid()::text);
exception when duplicate_object then null; end $$;
do $$ begin
  create policy own_feedback on feedback_responses using (user_id::text = auth.uid()::text);
exception when duplicate_object then null; end $$;
