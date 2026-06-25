-- ============================================================================
-- K-GPT · Migration 009 — introductory launch pricing
-- Monthly ₹99 / 30d · Semester ₹349 / 140d  (prices GST-inclusive).
-- Prices are stored in PAISE. Idempotent; safe to re-run.
-- Annual left as-is; deactivate it below if you only want to sell the two intro
-- plans during launch (uncomment the last line).
-- ============================================================================

update plans set price_inr = 9900,  duration_days = 30,  name = 'Monthly Access (₹99)',     active = true where code = 'monthly';
update plans set price_inr = 34900, duration_days = 140, name = 'Semester Access (₹349)',    active = true where code = 'semester';

-- Ensure both plans exist even on a fresh DB.
insert into plans (code, name, price_inr, duration_days, tier, active) values
  ('monthly',  'Monthly Access (₹99)',   9900,  30,  'monthly', true),
  ('semester', 'Semester Access (₹349)', 34900, 140, 'normal',  true)
on conflict (code) do update
  set name = excluded.name, price_inr = excluded.price_inr,
      duration_days = excluded.duration_days, tier = excluded.tier, active = true;

-- Optional: hide the annual plan during the intro launch.
-- update plans set active = false where code = 'annual';
