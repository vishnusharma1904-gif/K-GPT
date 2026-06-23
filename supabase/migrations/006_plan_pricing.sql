-- ============================================================================
-- K-GPT · Migration 006 — plan pricing update
-- Monthly ₹100 / 30d · Semester ₹500 / 140d · Annual ₹1000 / 365d.
-- Prices are in paise. Idempotent; safe to run after 005.
-- ============================================================================

update plans set price_inr = 10000,  duration_days = 30  where code = 'monthly';
update plans set price_inr = 50000,  duration_days = 140 where code = 'semester';
update plans set price_inr = 100000, duration_days = 365 where code = 'annual';

-- Make sure all three exist even on a fresh DB that somehow skipped seeds.
insert into plans (code, name, price_inr, duration_days, tier, active) values
  ('monthly',  'Monthly Access (₹100)',  10000,  30,  'monthly', true),
  ('semester', 'Semester Access (₹500)', 50000,  140, 'normal',  true),
  ('annual',   'Annual Access (₹1000)',  100000, 365, 'normal',  true)
on conflict (code) do update
  set name = excluded.name, price_inr = excluded.price_inr,
      duration_days = excluded.duration_days, tier = excluded.tier, active = true;
