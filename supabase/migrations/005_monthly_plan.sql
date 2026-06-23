-- ============================================================================
-- K-GPT · Migration 005 — temporary ₹100 monthly plan (Heavy-ish daily cap)
-- Adds a 'monthly' plan that maps to the new 'monthly' tier (150,000 tokens/day).
-- Idempotent; safe to run after 004.
-- ============================================================================

insert into plans (code, name, price_inr, duration_days, tier, active) values
  ('monthly', 'Monthly Access (₹100)', 10000, 30, 'monthly', true)
on conflict (code) do update
  set name = excluded.name,
      price_inr = excluded.price_inr,
      duration_days = excluded.duration_days,
      tier = excluded.tier,
      active = true;
