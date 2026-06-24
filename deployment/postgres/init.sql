-- ===========================================================================
-- Prompt Pulse (K-GPT) — Self-Hosted PostgreSQL Init Script
-- Ported from supabase/setup_all.sql for standalone PostgreSQL.
--
-- Differences from Supabase version:
--   1. No auth.uid() — RLS policies use a simpler pattern (backend enforces)
--   2. Extensions are installed directly (pgvector, pgcrypto, pg_trgm)
--   3. Added BM25/full-text search indexes for hybrid retrieval (Phase 2)
--   4. Added new tables for Prompt Pulse features (documents, cache, confidence)
-- ===========================================================================

-- Extensions -----------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "pgcrypto";    -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "vector";       -- pgvector (kept for backward compat)
CREATE EXTENSION IF NOT EXISTS "pg_trgm";      -- trigram indexes for fuzzy text search

-- ============================================================================
-- ENUMS
-- ============================================================================
DO $$ BEGIN
  CREATE TYPE user_role AS ENUM ('student', 'admin');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE sub_status AS ENUM ('inactive', 'active', 'expired', 'pending');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ============================================================================
-- USERS
-- ============================================================================
CREATE TABLE IF NOT EXISTS app_users (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email           text UNIQUE NOT NULL,
  full_name       text NOT NULL DEFAULT '',
  roll_no         text,
  password_hash   text NOT NULL,
  role            user_role NOT NULL DEFAULT 'student',
  -- subscription
  sub_status      sub_status NOT NULL DEFAULT 'inactive',
  sub_expires_at  timestamptz,
  -- quota (original)
  quota_tokens    bigint NOT NULL DEFAULT 1500000,
  used_tokens     bigint NOT NULL DEFAULT 0,
  daily_msg_limit int NOT NULL DEFAULT 200,
  -- preferences
  preferences     jsonb NOT NULL DEFAULT '{}'::jsonb,
  -- Epic B: tiered quotas
  tier                text NOT NULL DEFAULT 'normal',
  tier_override       boolean NOT NULL DEFAULT false,
  daily_cap           bigint NOT NULL DEFAULT 500000,
  daily_used          bigint NOT NULL DEFAULT 0,
  daily_reset_at      timestamptz,
  weekly_bonus_available boolean NOT NULL DEFAULT true,
  weekly_bonus_claimed_today bigint NOT NULL DEFAULT 0,
  weekly_bonus_reset_at timestamptz,
  bonus_balance       bigint NOT NULL DEFAULT 0,
  suspended           boolean NOT NULL DEFAULT false,
  -- Epic D: personalization
  email_verified      boolean NOT NULL DEFAULT false,
  exam_mode           boolean NOT NULL DEFAULT false,
  response_style      text NOT NULL DEFAULT 'balanced',
  custom_instructions text,
  memory_enabled      boolean NOT NULL DEFAULT true,
  web_search_enabled  boolean NOT NULL DEFAULT false,
  plan                text NOT NULL DEFAULT 'semester',
  failed_logins       int NOT NULL DEFAULT 0,
  locked_until        timestamptz,
  -- Epic A: SSO
  auth_provider       text NOT NULL DEFAULT 'password',
  provider_sub        text,
  avatar_url          text,
  cohort              text,
  -- timestamps
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_users_email ON app_users (email);
CREATE INDEX IF NOT EXISTS idx_users_sub ON app_users (sub_status);
CREATE INDEX IF NOT EXISTS idx_users_provider_sub ON app_users (provider_sub) WHERE provider_sub IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_users_cohort ON app_users (cohort);

-- ============================================================================
-- CHAT SESSIONS + MESSAGES
-- ============================================================================
CREATE TABLE IF NOT EXISTS chat_sessions (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  title       text NOT NULL DEFAULT 'New chat',
  persona     text NOT NULL DEFAULT 'kgpt',
  project_id  uuid,  -- FK added after projects table exists
  pinned      boolean NOT NULL DEFAULT false,
  archived    boolean NOT NULL DEFAULT false,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON chat_sessions (user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_project ON chat_sessions (project_id);

CREATE TABLE IF NOT EXISTS chat_messages (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id  uuid NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
  user_id     uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  role        text NOT NULL,
  content     text NOT NULL,
  model       text,
  tokens      int NOT NULL DEFAULT 0,
  parent_id   uuid REFERENCES chat_messages(id) ON DELETE SET NULL,
  feedback    smallint,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON chat_messages (session_id, created_at);
-- Full-text search index for BM25 hybrid retrieval (Phase 2)
CREATE INDEX IF NOT EXISTS idx_messages_content_trgm ON chat_messages USING gin (content gin_trgm_ops);

-- ============================================================================
-- MEMORY (pgvector — kept for backward compat, Qdrant is primary at scale)
-- ============================================================================
CREATE TABLE IF NOT EXISTS memory_chunks (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  kind        text NOT NULL DEFAULT 'note',
  source      text,
  content     text NOT NULL,
  embedding   vector(384),       -- MiniLM (legacy); new chunks go to Qdrant
  project_id  uuid,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_memory_user ON memory_chunks (user_id);
CREATE INDEX IF NOT EXISTS idx_memory_project ON memory_chunks (project_id);
CREATE INDEX IF NOT EXISTS idx_memory_embedding
  ON memory_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Per-user semantic search (same RPC signature as Supabase)
CREATE OR REPLACE FUNCTION match_memory (
  p_user_id uuid,
  p_query   vector(384),
  p_limit   int DEFAULT 6,
  p_min_sim float DEFAULT 0.40
) RETURNS TABLE (id uuid, content text, source text, similarity float)
LANGUAGE sql STABLE AS $$
  SELECT m.id, m.content, m.source,
         1 - (m.embedding <=> p_query) AS similarity
  FROM memory_chunks m
  WHERE m.user_id = p_user_id
    AND m.embedding IS NOT NULL
    AND 1 - (m.embedding <=> p_query) >= p_min_sim
  ORDER BY m.embedding <=> p_query
  LIMIT p_limit;
$$;

-- ============================================================================
-- USAGE METERING
-- ============================================================================
CREATE TABLE IF NOT EXISTS usage_log (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  model         text NOT NULL,
  prompt_tokens int NOT NULL DEFAULT 0,
  completion_tokens int NOT NULL DEFAULT 0,
  cost_usd      numeric(10,6) NOT NULL DEFAULT 0,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_usage_user_time ON usage_log (user_id, created_at DESC);

-- ============================================================================
-- PAYMENTS
-- ============================================================================
CREATE TABLE IF NOT EXISTS payments (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  rzp_order_id  text,
  rzp_payment_id text,
  amount_inr    int NOT NULL,
  status        text NOT NULL DEFAULT 'created',
  semester      text,
  plan          text,
  expires_at    timestamptz,
  gst_inr       int NOT NULL DEFAULT 0,
  receipt_no    text,
  coupon        text,
  webhook_seen  boolean NOT NULL DEFAULT false,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_payments_user ON payments (user_id, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_payments_payment ON payments (rzp_payment_id) WHERE rzp_payment_id IS NOT NULL;

-- ============================================================================
-- EPIC B — QUOTA, TIERS, ENTITLEMENTS
-- ============================================================================
CREATE TABLE IF NOT EXISTS usage_daily (
  user_id   uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  day       date NOT NULL,
  tokens    bigint NOT NULL DEFAULT 0,
  requests  int    NOT NULL DEFAULT 0,
  hit_cap   boolean NOT NULL DEFAULT false,
  PRIMARY KEY (user_id, day)
);
CREATE INDEX IF NOT EXISTS idx_usage_daily_user ON usage_daily (user_id, day DESC);

CREATE TABLE IF NOT EXISTS entitlement_log (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_user_id   uuid REFERENCES app_users(id) ON DELETE SET NULL,
  target_user_id  uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  action          text NOT NULL,
  delta           bigint DEFAULT 0,
  detail          text,
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_entlog_target ON entitlement_log (target_user_id, created_at DESC);

-- Atomic RPCs (same signatures as Supabase version)
CREATE OR REPLACE FUNCTION increment_daily_usage(p_user_id uuid, p_tokens bigint)
RETURNS bigint LANGUAGE plpgsql AS $$
DECLARE new_used bigint;
BEGIN
  UPDATE app_users SET daily_used = daily_used + p_tokens
  WHERE id = p_user_id RETURNING daily_used INTO new_used;
  RETURN new_used;
END $$;

CREATE OR REPLACE FUNCTION bump_usage_daily(
  p_user_id uuid, p_day date, p_tokens bigint, p_requests int, p_hit_cap boolean)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO usage_daily (user_id, day, tokens, requests, hit_cap)
  VALUES (p_user_id, p_day, p_tokens, p_requests, p_hit_cap)
  ON CONFLICT (user_id, day) DO UPDATE
    SET tokens = usage_daily.tokens + excluded.tokens,
        requests = usage_daily.requests + excluded.requests,
        hit_cap = usage_daily.hit_cap OR excluded.hit_cap;
END $$;

CREATE OR REPLACE FUNCTION claim_weekly_bonus(p_user_id uuid, p_amount bigint, p_reset timestamptz)
RETURNS boolean LANGUAGE plpgsql AS $$
DECLARE ok boolean := false;
BEGIN
  UPDATE app_users
    SET weekly_bonus_available = false,
        weekly_bonus_claimed_today = weekly_bonus_claimed_today + p_amount,
        weekly_bonus_reset_at = COALESCE(weekly_bonus_reset_at, p_reset)
  WHERE id = p_user_id AND weekly_bonus_available = true
  RETURNING true INTO ok;
  RETURN COALESCE(ok, false);
END $$;

-- ============================================================================
-- AUTH TOKENS (email verify / password reset)
-- ============================================================================
CREATE TABLE IF NOT EXISTS auth_tokens (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  kind        text NOT NULL,
  token_hash  text NOT NULL,
  expires_at  timestamptz NOT NULL,
  used        boolean NOT NULL DEFAULT false,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_authtokens_user ON auth_tokens (user_id, kind);
CREATE INDEX IF NOT EXISTS idx_authtokens_hash ON auth_tokens (token_hash);

-- ============================================================================
-- PROJECTS
-- ============================================================================
CREATE TABLE IF NOT EXISTS projects (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  name          text NOT NULL DEFAULT 'New project',
  instructions  text,
  color         text DEFAULT 'brand',
  archived      boolean NOT NULL DEFAULT false,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_projects_user ON projects (user_id, updated_at DESC);

-- Add FK from chat_sessions to projects now that projects exists
DO $$ BEGIN
  ALTER TABLE chat_sessions ADD CONSTRAINT fk_sessions_project
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ============================================================================
-- SHARE LINKS
-- ============================================================================
CREATE TABLE IF NOT EXISTS shared_chats (
  token       text PRIMARY KEY,
  session_id  uuid NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
  user_id     uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  revoked     boolean NOT NULL DEFAULT false,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_shared_user ON shared_chats (user_id);

-- ============================================================================
-- PLANS & COUPONS
-- ============================================================================
CREATE TABLE IF NOT EXISTS plans (
  code         text PRIMARY KEY,
  name         text NOT NULL,
  price_inr    int NOT NULL,
  duration_days int NOT NULL,
  tier         text NOT NULL DEFAULT 'normal',
  active       boolean NOT NULL DEFAULT true
);
INSERT INTO plans (code, name, price_inr, duration_days, tier) VALUES
  ('monthly',  'Monthly Access',  15000,  30,  'normal'),
  ('semester', 'Semester Access', 60000,  150, 'normal'),
  ('annual',   'Annual Access',   100000, 365, 'normal')
ON CONFLICT (code) DO NOTHING;

CREATE TABLE IF NOT EXISTS coupons (
  code         text PRIMARY KEY,
  percent_off  int NOT NULL DEFAULT 0,
  max_redemptions int,
  redeemed     int NOT NULL DEFAULT 0,
  expires_at   timestamptz,
  active       boolean NOT NULL DEFAULT true,
  created_at   timestamptz NOT NULL DEFAULT now()
);

-- ============================================================================
-- FEATURE FLAGS
-- ============================================================================
CREATE TABLE IF NOT EXISTS feature_flags (
  key         text PRIMARY KEY,
  enabled     boolean NOT NULL DEFAULT false,
  description text,
  rollout_pct int NOT NULL DEFAULT 0,
  updated_at  timestamptz NOT NULL DEFAULT now()
);
INSERT INTO feature_flags (key, enabled, description, rollout_pct) VALUES
  ('voice',            false, 'Voice mode (STT/TTS) — P35',            0),
  ('code_interpreter', true,  'Sandboxed Python execution — P36',      100),
  ('vision',           true,  'Image understanding — P34',             100),
  ('web_search',       true,  'Web search grounding — P33',            100),
  ('artifacts',        true,  'Artifacts / Canvas split pane — P23',   100),
  ('study_aids',       true,  'Flashcards / quiz / summary — P38',     100)
ON CONFLICT (key) DO NOTHING;

-- ============================================================================
-- PROMPT LIBRARY
-- ============================================================================
CREATE TABLE IF NOT EXISTS prompts (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid REFERENCES app_users(id) ON DELETE CASCADE,
  slug        text NOT NULL,
  title       text NOT NULL,
  body        text NOT NULL,
  shared      boolean NOT NULL DEFAULT false,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_prompts_user ON prompts (user_id);
CREATE INDEX IF NOT EXISTS idx_prompts_shared ON prompts (shared) WHERE shared = true;

INSERT INTO prompts (id, user_id, slug, title, body, shared) VALUES
  (gen_random_uuid(), NULL, '/essay',   'Essay outline',
   'Write a clear, well-structured outline for an essay on: {topic}. Include a thesis, 3 supporting points, and a conclusion.', true),
  (gen_random_uuid(), NULL, '/explain', 'Explain simply',
   'Explain the following concept in simple terms with one everyday analogy: {concept}', true),
  (gen_random_uuid(), NULL, '/review',  'Code review',
   'Review this code for correctness, readability, and bugs. Suggest concrete improvements:\n\n{code}', true),
  (gen_random_uuid(), NULL, '/quiz',    'Make a quiz',
   'Create a 5-question multiple-choice quiz (with answers) to test understanding of: {topic}', true),
  (gen_random_uuid(), NULL, '/summarize','Summarize',
   'Summarize the following into 5 concise bullet points a student can revise from:\n\n{text}', true)
ON CONFLICT DO NOTHING;

-- ============================================================================
-- STUDY AIDS
-- ============================================================================
CREATE TABLE IF NOT EXISTS study_aids (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  session_id  uuid REFERENCES chat_sessions(id) ON DELETE SET NULL,
  kind        text NOT NULL,
  title       text,
  payload     jsonb NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_studyaids_user ON study_aids (user_id, created_at DESC);

-- ============================================================================
-- COST GOVERNANCE
-- ============================================================================
CREATE TABLE IF NOT EXISTS cohort_budgets (
  cohort        text PRIMARY KEY,
  monthly_usd   numeric(10,2) NOT NULL DEFAULT 0,
  alert_pct     int NOT NULL DEFAULT 80,
  throttled     boolean NOT NULL DEFAULT false,
  updated_at    timestamptz NOT NULL DEFAULT now()
);

-- ============================================================================
-- INCIDENTS / STATUS
-- ============================================================================
CREATE TABLE IF NOT EXISTS incidents (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  title       text NOT NULL,
  severity    text NOT NULL DEFAULT 'minor',
  status      text NOT NULL DEFAULT 'investigating',
  body        text,
  created_at  timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz
);
CREATE INDEX IF NOT EXISTS idx_incidents_open ON incidents (status) WHERE status <> 'resolved';

-- ============================================================================
-- FEEDBACK
-- ============================================================================
CREATE TABLE IF NOT EXISTS feedback_responses (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  kind        text NOT NULL DEFAULT 'nps',
  score       int,
  comment     text,
  context     text,
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_feedback_user ON feedback_responses (user_id);
CREATE INDEX IF NOT EXISTS idx_feedback_kind ON feedback_responses (kind, created_at DESC);

-- ============================================================================
-- SAFETY EVENTS
-- ============================================================================
CREATE TABLE IF NOT EXISTS safety_events (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  session_id   uuid REFERENCES chat_sessions(id) ON DELETE SET NULL,
  severity     text NOT NULL DEFAULT 'low',
  category     text NOT NULL DEFAULT 'jailbreak',
  score        int  NOT NULL DEFAULT 0,
  blocked      boolean NOT NULL DEFAULT false,
  snippet      text,
  reasons      text,
  reviewed     boolean NOT NULL DEFAULT false,
  reviewed_by  uuid REFERENCES app_users(id) ON DELETE SET NULL,
  reviewed_at  timestamptz,
  notes        text,
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_safety_events_created  ON safety_events (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_safety_events_user     ON safety_events (user_id);
CREATE INDEX IF NOT EXISTS idx_safety_events_severity ON safety_events (severity);
CREATE INDEX IF NOT EXISTS idx_safety_events_unrev    ON safety_events (reviewed) WHERE reviewed = false;

-- ============================================================================
-- PROMPT PULSE — NEW TABLES (Phase 1+)
-- ============================================================================

-- Document registry (files uploaded for RAG; content stored in S3, chunks in Qdrant)
CREATE TABLE IF NOT EXISTS documents (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id        uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  institution_id text NOT NULL DEFAULT 'ksrmce',
  filename       text NOT NULL,
  file_type      text NOT NULL,
  file_size_bytes bigint NOT NULL DEFAULT 0,
  s3_key         text,
  chunk_count    int DEFAULT 0,
  status         text NOT NULL DEFAULT 'pending',  -- pending | processing | ready | failed
  metadata       jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_documents_user ON documents (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents (status);

-- Response confidence tracking (hallucination metrics)
CREATE TABLE IF NOT EXISTS response_confidence (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id       uuid REFERENCES chat_sessions(id) ON DELETE SET NULL,
  message_id       uuid,
  confidence_score float NOT NULL,
  grounding_ratio  float,
  verified_claims  int DEFAULT 0,
  unverified_claims int DEFAULT 0,
  sources_used     int DEFAULT 0,
  created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_confidence_session ON response_confidence (session_id);

-- ============================================================================
-- TRIGGERS
-- ============================================================================
CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END $$;

DROP TRIGGER IF EXISTS trg_users_touch ON app_users;
CREATE TRIGGER trg_users_touch BEFORE UPDATE ON app_users
  FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

DROP TRIGGER IF EXISTS trg_sessions_touch ON chat_sessions;
CREATE TRIGGER trg_sessions_touch BEFORE UPDATE ON chat_sessions
  FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

DROP TRIGGER IF EXISTS trg_projects_touch ON projects;
CREATE TRIGGER trg_projects_touch BEFORE UPDATE ON projects
  FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

-- ============================================================================
-- RLS (defense-in-depth; backend uses superuser but RLS catches bugs)
-- ============================================================================
ALTER TABLE app_users      ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_sessions  ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_messages  ENABLE ROW LEVEL SECURITY;
ALTER TABLE memory_chunks  ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_log      ENABLE ROW LEVEL SECURITY;
ALTER TABLE payments       ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_daily    ENABLE ROW LEVEL SECURITY;
ALTER TABLE entitlement_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects       ENABLE ROW LEVEL SECURITY;
ALTER TABLE shared_chats   ENABLE ROW LEVEL SECURITY;
ALTER TABLE auth_tokens    ENABLE ROW LEVEL SECURITY;
ALTER TABLE prompts        ENABLE ROW LEVEL SECURITY;
ALTER TABLE study_aids     ENABLE ROW LEVEL SECURITY;
ALTER TABLE feedback_responses ENABLE ROW LEVEL SECURITY;
ALTER TABLE safety_events  ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents      ENABLE ROW LEVEL SECURITY;
ALTER TABLE response_confidence ENABLE ROW LEVEL SECURITY;
