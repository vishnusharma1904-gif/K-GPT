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
