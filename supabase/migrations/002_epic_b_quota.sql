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
