-- ============================================================================
-- K-GPT · COMBINED DATABASE SETUP (run once in Supabase SQL Editor)
-- Runs: schema.sql + migrations 002 + 003 + 004, in order. Idempotent.
-- ============================================================================

-- ########## 1/4 · schema.sql ##########
-- ============================================================================
-- K-GPT  ·  Supabase / Postgres schema
-- Multi-tenant campus AI for KSRM College of Engineering
-- Run this in the Supabase SQL editor (or `psql < schema.sql`).
-- ============================================================================

-- Extensions -----------------------------------------------------------------
create extension if not exists "pgcrypto";   -- gen_random_uuid()
create extension if not exists "vector";      -- pgvector (per-user RAG)

-- ============================================================================
-- ENUMS
-- ============================================================================
do $$ begin
  create type user_role as enum ('student', 'admin');
exception when duplicate_object then null; end $$;

do $$ begin
  create type sub_status as enum ('inactive', 'active', 'expired', 'pending');
exception when duplicate_object then null; end $$;

-- ============================================================================
-- USERS  (one row per person; gated to college email at signup)
-- ============================================================================
create table if not exists app_users (
  id              uuid primary key default gen_random_uuid(),
  email           text unique not null,
  full_name       text not null default '',
  roll_no         text,                          -- parsed from college email
  password_hash   text not null,
  role            user_role not null default 'student',
  -- subscription / access -----------------------------------------------------
  sub_status      sub_status not null default 'inactive',
  sub_expires_at  timestamptz,                   -- end of paid semester
  -- usage quota (reset each billing period) -----------------------------------
  quota_tokens    bigint not null default 1500000, -- ~ generous semester budget
  used_tokens     bigint not null default 0,
  daily_msg_limit int not null default 200,
  -- metadata ------------------------------------------------------------------
  preferences     jsonb not null default '{}'::jsonb,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);
create index if not exists idx_users_email on app_users (email);
create index if not exists idx_users_sub on app_users (sub_status);

-- ============================================================================
-- CHAT SESSIONS + MESSAGES  (strictly scoped by user_id)
-- ============================================================================
create table if not exists chat_sessions (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references app_users(id) on delete cascade,
  title       text not null default 'New chat',
  persona     text not null default 'kgpt',
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create index if not exists idx_sessions_user on chat_sessions (user_id, updated_at desc);

create table if not exists chat_messages (
  id          uuid primary key default gen_random_uuid(),
  session_id  uuid not null references chat_sessions(id) on delete cascade,
  user_id     uuid not null references app_users(id) on delete cascade,
  role        text not null,                 -- 'user' | 'assistant' | 'system'
  content     text not null,
  model       text,                          -- which model answered
  tokens      int not null default 0,
  created_at  timestamptz not null default now()
);
create index if not exists idx_messages_session on chat_messages (session_id, created_at);

-- ============================================================================
-- MEMORY  (per-user RAG via pgvector; 384-dim MiniLM embeddings)
-- ============================================================================
create table if not exists memory_chunks (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references app_users(id) on delete cascade,
  kind        text not null default 'note',  -- note | document | conversation
  source      text,                          -- filename / origin
  content     text not null,
  embedding   vector(384),
  created_at  timestamptz not null default now()
);
create index if not exists idx_memory_user on memory_chunks (user_id);
-- ANN index for fast per-user similarity search
create index if not exists idx_memory_embedding
  on memory_chunks using ivfflat (embedding vector_cosine_ops) with (lists = 100);

-- Per-user semantic search helper (cosine distance, user-scoped) -------------
create or replace function match_memory (
  p_user_id uuid,
  p_query   vector(384),
  p_limit   int default 6,
  p_min_sim float default 0.40
) returns table (id uuid, content text, source text, similarity float)
language sql stable as $$
  select m.id, m.content, m.source,
         1 - (m.embedding <=> p_query) as similarity
  from memory_chunks m
  where m.user_id = p_user_id
    and m.embedding is not null
    and 1 - (m.embedding <=> p_query) >= p_min_sim
  order by m.embedding <=> p_query
  limit p_limit;
$$;

-- ============================================================================
-- USAGE METERING  (every LLM call logged for cost/quota/analytics)
-- ============================================================================
create table if not exists usage_log (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null references app_users(id) on delete cascade,
  model         text not null,
  prompt_tokens int not null default 0,
  completion_tokens int not null default 0,
  cost_usd      numeric(10,6) not null default 0,
  created_at    timestamptz not null default now()
);
create index if not exists idx_usage_user_time on usage_log (user_id, created_at desc);

-- ============================================================================
-- PAYMENTS  (Razorpay order/payment audit trail)
-- ============================================================================
create table if not exists payments (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null references app_users(id) on delete cascade,
  rzp_order_id  text,
  rzp_payment_id text,
  amount_inr    int not null,                  -- in paise
  status        text not null default 'created', -- created|paid|failed
  semester      text,                           -- e.g. '2026-ODD'
  created_at    timestamptz not null default now()
);
create index if not exists idx_payments_user on payments (user_id, created_at desc);

-- ============================================================================
-- ROW-LEVEL SECURITY
-- The backend connects with the service-role key and enforces user scoping in
-- code, but RLS is enabled as defense-in-depth so a bug can never leak data
-- across tenants if the anon/auth key is ever used.
-- ============================================================================
alter table app_users      enable row level security;
alter table chat_sessions  enable row level security;
alter table chat_messages  enable row level security;
alter table memory_chunks  enable row level security;
alter table usage_log      enable row level security;
alter table payments       enable row level security;

-- Service role bypasses RLS automatically. These policies cover the case where
-- you later wire Supabase Auth and use auth.uid() from the client directly.
do $$ begin
  create policy own_sessions on chat_sessions
    using (user_id::text = auth.uid()::text);
exception when duplicate_object then null; end $$;
do $$ begin
  create policy own_messages on chat_messages
    using (user_id::text = auth.uid()::text);
exception when duplicate_object then null; end $$;
do $$ begin
  create policy own_memory on memory_chunks
    using (user_id::text = auth.uid()::text);
exception when duplicate_object then null; end $$;
do $$ begin
  create policy own_usage on usage_log
    using (user_id::text = auth.uid()::text);
exception when duplicate_object then null; end $$;
do $$ begin
  create policy own_payments on payments
    using (user_id::text = auth.uid()::text);
exception when duplicate_object then null; end $$;

-- updated_at trigger ----------------------------------------------------------
create or replace function touch_updated_at() returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end $$;

drop trigger if exists trg_users_touch on app_users;
create trigger trg_users_touch before update on app_users
  for each row execute function touch_updated_at();

drop trigger if exists trg_sessions_touch on chat_sessions;
create trigger trg_sessions_touch before update on chat_sessions
  for each row execute function touch_updated_at();

-- ########## 2/4 · 002_epic_b_quota.sql ##########
-- ============================================================================
-- K-GPT · Migration 002 — Epic B: Quota, Tiers & Entitlements
-- Adds tiered daily caps, weekly bonus, admin grants, usage history, audit log.
-- Safe to run on top of schema.sql (idempotent where possible).
-- ============================================================================

-- --- New columns on app_users ----------------------------------------------
alter table app_users add column if not exists tier text not null default 'normal';        -- normal | heavy
alter table app_users add column if not exists tier_override boolean not null default false; -- admin pin; skips auto-tiering
alter table app_users add column if not exists daily_cap bigint not null default 500000;     -- derived from tier
alter table app_users add column if not exists daily_used bigint not null default 0;
alter table app_users add column if not exists daily_reset_at timestamptz;                    -- next 00:00 IST
alter table app_users add column if not exists weekly_bonus_available boolean not null default true;
alter table app_users add column if not exists weekly_bonus_claimed_today bigint not null default 0;
alter table app_users add column if not exists weekly_bonus_reset_at timestamptz;
alter table app_users add column if not exists bonus_balance bigint not null default 0;       -- admin one-off grants (persistent)
alter table app_users add column if not exists suspended boolean not null default false;

-- --- Per-day usage rollups (for auto-tiering + admin analytics) -------------
create table if not exists usage_daily (
  user_id   uuid not null references app_users(id) on delete cascade,
  day       date not null,
  tokens    bigint not null default 0,
  requests  int    not null default 0,
  hit_cap   boolean not null default false,
  primary key (user_id, day)
);
create index if not exists idx_usage_daily_user on usage_daily (user_id, day desc);

-- --- Entitlement audit log (every grant / reset / tier change) --------------
create table if not exists entitlement_log (
  id              uuid primary key default gen_random_uuid(),
  actor_user_id   uuid references app_users(id) on delete set null,  -- admin who acted
  target_user_id  uuid not null references app_users(id) on delete cascade,
  action          text not null,        -- reset_daily | grant_tokens | set_tier | refresh_bonus | suspend | restore
  delta           bigint default 0,
  detail          text,
  created_at      timestamptz not null default now()
);
create index if not exists idx_entlog_target on entitlement_log (target_user_id, created_at desc);

alter table usage_daily     enable row level security;
alter table entitlement_log enable row level security;

-- ============================================================================
-- ATOMIC RPCs — concurrency-safe increments / claims, done in the DB
-- ============================================================================

-- Add usage to the running daily counter atomically; returns the new value.
create or replace function increment_daily_usage(p_user_id uuid, p_tokens bigint)
returns bigint language plpgsql as $$
declare new_used bigint;
begin
  update app_users set daily_used = daily_used + p_tokens
  where id = p_user_id returning daily_used into new_used;
  return new_used;
end $$;

-- Upsert the per-day rollup (called at reset-snapshot time).
create or replace function bump_usage_daily(
  p_user_id uuid, p_day date, p_tokens bigint, p_requests int, p_hit_cap boolean)
returns void language plpgsql as $$
begin
  insert into usage_daily (user_id, day, tokens, requests, hit_cap)
  values (p_user_id, p_day, p_tokens, p_requests, p_hit_cap)
  on conflict (user_id, day) do update
    set tokens = usage_daily.tokens + excluded.tokens,
        requests = usage_daily.requests + excluded.requests,
        hit_cap = usage_daily.hit_cap or excluded.hit_cap;
end $$;

-- Claim the once-per-week bonus atomically: only succeeds if available.
-- Returns true if the claim was applied.
create or replace function claim_weekly_bonus(p_user_id uuid, p_amount bigint, p_reset timestamptz)
returns boolean language plpgsql as $$
declare ok boolean := false;
begin
  update app_users
    set weekly_bonus_available = false,
        weekly_bonus_claimed_today = weekly_bonus_claimed_today + p_amount,
        weekly_bonus_reset_at = coalesce(weekly_bonus_reset_at, p_reset)
  where id = p_user_id and weekly_bonus_available = true
  returning true into ok;
  return coalesce(ok, false);
end $$;

-- ########## 3/4 · 003_phases_d_to_i.sql ##########
-- ============================================================================
-- K-GPT · Migration 003 — Epics A/C/D/E/G/H feature foundations
-- Adds: auth hardening, custom instructions/styles, exam mode, projects,
--       file-memory scoping, share links, message feedback, plans/coupons,
--       billing lifecycle fields. Idempotent; safe to run after 002.
-- ============================================================================

-- --- app_users: personalization, integrity, auth, memory toggle ------------
alter table app_users add column if not exists email_verified      boolean not null default false;
alter table app_users add column if not exists exam_mode            boolean not null default false;   -- P40 academic-integrity overlay
alter table app_users add column if not exists response_style       text    not null default 'balanced'; -- P25 concise|balanced|detailed|formal
alter table app_users add column if not exists custom_instructions  text;                              -- P25 "about me / how to respond"
alter table app_users add column if not exists memory_enabled       boolean not null default true;     -- P31 memory on/off
alter table app_users add column if not exists web_search_enabled   boolean not null default false;    -- P33 default preference
alter table app_users add column if not exists plan                 text    not null default 'semester';
alter table app_users add column if not exists failed_logins        int     not null default 0;        -- P2 brute-force lockout
alter table app_users add column if not exists locked_until         timestamptz;

-- --- Email verification + password reset tokens (P2) ------------------------
create table if not exists auth_tokens (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references app_users(id) on delete cascade,
  kind        text not null,                       -- 'verify' | 'reset'
  token_hash  text not null,                       -- sha256 of the emailed token
  expires_at  timestamptz not null,
  used        boolean not null default false,
  created_at  timestamptz not null default now()
);
create index if not exists idx_authtokens_user on auth_tokens (user_id, kind);
create index if not exists idx_authtokens_hash on auth_tokens (token_hash);

-- --- Projects: group chats + shared knowledge (P20 / P30) -------------------
create table if not exists projects (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null references app_users(id) on delete cascade,
  name          text not null default 'New project',
  instructions  text,                              -- per-project system overlay
  color         text default 'brand',
  archived      boolean not null default false,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
create index if not exists idx_projects_user on projects (user_id, updated_at desc);

-- chat_sessions: project grouping + pin/archive + title search (P20)
alter table chat_sessions add column if not exists project_id uuid references projects(id) on delete set null;
alter table chat_sessions add column if not exists pinned     boolean not null default false;
alter table chat_sessions add column if not exists archived   boolean not null default false;
create index if not exists idx_sessions_project on chat_sessions (project_id);

-- memory_chunks: scope to a project (P30) + simple full-text on title (P20)
alter table memory_chunks add column if not exists project_id uuid references projects(id) on delete cascade;
create index if not exists idx_memory_project on memory_chunks (project_id);

-- --- Share links (P27) ------------------------------------------------------
create table if not exists shared_chats (
  token       text primary key,                    -- public, unguessable
  session_id  uuid not null references chat_sessions(id) on delete cascade,
  user_id     uuid not null references app_users(id) on delete cascade,
  revoked     boolean not null default false,
  created_at  timestamptz not null default now()
);
create index if not exists idx_shared_user on shared_chats (user_id);

-- --- Message feedback + branching (P26) -------------------------------------
alter table chat_messages add column if not exists parent_id uuid references chat_messages(id) on delete set null;
alter table chat_messages add column if not exists feedback  smallint;   -- -1 down, +1 up, null none

-- --- Plans & coupons (P16 / P18) --------------------------------------------
create table if not exists plans (
  code         text primary key,                   -- 'semester' | 'annual'
  name         text not null,
  price_inr    int not null,                        -- in paise
  duration_days int not null,
  tier         text not null default 'normal',      -- entitlement tier on purchase
  active       boolean not null default true
);
insert into plans (code, name, price_inr, duration_days, tier) values
  ('semester', 'Semester Access', 100000, 183, 'normal'),
  ('annual',   'Annual Access',   180000, 365, 'normal')
on conflict (code) do nothing;

create table if not exists coupons (
  code         text primary key,
  percent_off  int not null default 0,              -- 0-100
  max_redemptions int,
  redeemed     int not null default 0,
  expires_at   timestamptz,
  active       boolean not null default true,
  created_at   timestamptz not null default now()
);

-- --- payments: billing lifecycle + GST/receipt fields (P15 / P17) ----------
alter table payments add column if not exists plan        text;
alter table payments add column if not exists expires_at  timestamptz;
alter table payments add column if not exists gst_inr     int not null default 0;     -- paise
alter table payments add column if not exists receipt_no  text;
alter table payments add column if not exists coupon      text;
alter table payments add column if not exists webhook_seen boolean not null default false;
create unique index if not exists idx_payments_payment on payments (rzp_payment_id) where rzp_payment_id is not null;

-- --- RLS on the new tenant tables ------------------------------------------
alter table projects     enable row level security;
alter table shared_chats enable row level security;
alter table auth_tokens  enable row level security;

do $$ begin
  create policy own_projects on projects using (user_id::text = auth.uid()::text);
exception when duplicate_object then null; end $$;

drop trigger if exists trg_projects_touch on projects;
create trigger trg_projects_touch before update on projects
  for each row execute function touch_updated_at();

-- ########## 4/4 · 004_phases_remaining.sql ##########
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

-- ########## · migration 007 · safety monitoring ##########
create table if not exists safety_events (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null references app_users(id) on delete cascade,
  session_id   uuid references chat_sessions(id) on delete set null,
  severity     text not null default 'low',
  category     text not null default 'jailbreak',
  score        int  not null default 0,
  blocked      boolean not null default false,
  snippet      text,
  reasons      text,
  reviewed     boolean not null default false,
  reviewed_by  uuid references app_users(id) on delete set null,
  reviewed_at  timestamptz,
  notes        text,
  created_at   timestamptz not null default now()
);
create index if not exists idx_safety_events_created  on safety_events (created_at desc);
create index if not exists idx_safety_events_user     on safety_events (user_id);
create index if not exists idx_safety_events_severity on safety_events (severity);
create index if not exists idx_safety_events_unrev    on safety_events (reviewed) where reviewed = false;
alter table safety_events enable row level security;
