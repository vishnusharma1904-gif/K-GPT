# K-GPT — Reliability & Incident Runbook (P47)

This runbook covers uptime monitoring, the status page, provider-outage
behaviour, and backup/restore. It complements the in-app status surface at
`/status` and the admin incident controls under `/api/status/incidents`.

## 1. What's automated

- **Provider failover.** `smart_router` keeps a per-model circuit breaker: 3
  consecutive failures open the circuit for 120s and traffic fails over down the
  category's fallback chain. Open circuits surface on `/status` as "temporarily
  routed around" — chat keeps working.
- **Quota self-heal.** `entitlements.refresh()` runs on every request, so daily
  resets are correct even if the nightly job is missed.
- **Cost throttle.** The nightly sweep runs `cost_governance.enforce()` (P46),
  throttling any cohort over its monthly budget until spend resets.

## 2. Uptime monitoring (set this up)

Point an external monitor (UptimeRobot, BetterStack, Pingdom, or a GitHub
Actions cron) at:

- `GET /api/health` — liveness (returns 200 + provider key presence).
- `GET /api/status` — public status JSON (overall + degraded models + incidents).

Alert when either is non-200 for 2 consecutive checks (60s interval). Wire the
alert to the on-call channel.

## 3. Posting an incident

When something is wrong that failover won't fix (e.g. DB outage, all providers
down, a bad deploy):

1. `POST /api/status/incidents` (admin) `{title, severity, body}` —
   `severity` ∈ `minor|major|critical`. `critical` flips `/status` to **outage**.
2. Update progress: `PATCH /api/status/incidents/{id}` `{status}` —
   `investigating → identified → monitoring → resolved`.
3. Resolving sets `resolved_at` and clears it from the public page.

## 4. Provider-outage drill

1. Confirm in admin analytics / logs which provider is failing.
2. The circuit breaker should already be failing over — verify `/status`
   `degraded_models` lists it.
3. If an entire category is down (all fallbacks fail), temporarily disable the
   dependent feature flag (e.g. `vision`) via `PATCH /api/admin/flags/{key}`.
4. Post an incident if students are affected.

## 5. Backups & restore (Supabase)

- **Backups.** Supabase runs daily automated backups on paid plans. For the
  pilot, additionally export a logical dump weekly:
  `supabase db dump -f kgpt_backup_$(date +%F).sql` (or `pg_dump` against the
  connection string). Store off-site (e.g. a private bucket).
- **Restore test (do once before launch).** Spin up a scratch Supabase project,
  run `schema.sql` + migrations `002`→`004`, then `psql < kgpt_backup_*.sql`.
  Confirm row counts and that the app boots against it. Record the time-to-restore.
- **Migrations are idempotent** — re-running them is safe and is part of restore.

## 6. Rollback

- **Backend/frontend:** redeploy the previous green build (CI keeps artifacts).
- **DB migration:** migrations only *add* columns/tables (no destructive drops),
  so a code rollback is safe without a DB rollback.
