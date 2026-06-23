-- ============================================================================
-- Migration 007 — Safety monitoring / safeguarding (admin oversight)
-- Records jailbreak attempts, prompt-injection, and other flagged events so the
-- campus admin team can review and intervene. Scoped to campus plans in app code
-- (semester / monthly); annual "public" users are not logged here.
-- ============================================================================

create table if not exists safety_events (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null references app_users(id) on delete cascade,
  session_id   uuid references chat_sessions(id) on delete set null,
  severity     text not null default 'low',          -- low | medium | high
  category     text not null default 'jailbreak',    -- jailbreak | prompt_leak | self_harm | weapons | malware
  score        int  not null default 0,
  blocked      boolean not null default false,
  snippet      text,                                  -- short excerpt of the offending message
  reasons      text,                                  -- human-readable detection reasons
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

-- All access is via the service-role key from the backend (admin-gated in app
-- code). RLS stays enabled on the rest of the schema; this table is never read
-- with an end-user key.
alter table safety_events enable row level security;
