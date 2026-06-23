# K-GPT — Pilot → GA Runbook (P50)

A staged path from a one-department paid pilot to general availability across
KSRMCE, with instrumented feedback so decisions are data-driven.

## 1. Pre-pilot checklist

- [ ] DB migrations `002` → `003` → `004` applied to the production Supabase project.
- [ ] `.env` filled: `SUPABASE_*`, at least `GROQ_API_KEY`, `ADMIN_EMAILS`,
      `SECRET_KEY`, `RAZORPAY_*` (if charging), `GOOGLE_CLIENT_ID` (SSO).
- [ ] Academic-integrity (exam) mode reviewed with the HOD; enable per cohort.
- [ ] A cohort budget set for the pilot department (`PUT /api/admin/budgets`) so
      spend is capped (P46).
- [ ] Uptime monitor live against `/api/health` (see RELIABILITY.md).
- [ ] Restore test completed once.

## 2. Onboarding the pilot department

1. Collect the section's roll numbers.
2. Either **bulk-activate** them (`POST /api/admin/bulk-activate`
   `{roll_nos, months}`) for an institution-sponsored pilot, or issue a
   **coupon** (`POST /api/admin/coupons`) for self-serve paid signup.
3. Students sign in with their `@ksrmce.ac.in` Google account (one tap, no
   password to share — protects the budget).

## 3. Instrumenting feedback

- **In-app NPS / CSAT.** Prompt students to submit `POST /api/feedback`
  (`kind: nps`, score 0–10) after a week of use. Read the rollup at
  `GET /api/feedback/nps` (admin): NPS = %promoters(9–10) − %detractors(0–6).
- **Thumbs.** Per-message 👍/👎 already writes to `chat_messages.feedback`;
  review the ratio in admin analytics.
- **Usage & cost.** `GET /api/admin/analytics` → WAU, model mix, tier
  distribution, provider cost. Watch the cohort budget vs. spend.

## 4. Weekly pilot review (repeat)

Each week, capture: WAU, messages/active-user, NPS, thumbs ratio, cost/student,
top failure modes (from incidents + 👎 messages). Decide: fix, keep, or cut.

## 5. Success gates before widening

- NPS ≥ 30 (or improving week-over-week).
- Cost per active student within the per-cohort budget.
- No unresolved critical incidents in the final pilot week.
- Academic-integrity behaviour validated on real assignment prompts.

## 6. Staged rollout → GA

1. Pilot department (1 section) → 2 weeks.
2. Whole department (all sections) → 2 weeks, budgets per section.
3. Adjacent departments in waves, each gated on the success metrics above.
4. **GA:** open signup to the whole college, publish the `/status` page, and
   keep the weekly review cadence for the first term.

## 7. Rollback / pause

If cost spikes or a safety issue appears: throttle the cohort
(`POST /api/admin/budgets/enforce`), disable the affected feature flag, or
suspend accounts (`POST /api/admin/entitlements/suspend`) — all reversible and
audit-logged.
