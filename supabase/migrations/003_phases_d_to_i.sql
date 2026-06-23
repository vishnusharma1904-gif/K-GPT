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
