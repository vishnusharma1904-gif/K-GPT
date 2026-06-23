# K-GPT — Session Handoff

> Read this first when resuming work. It records **what exists, how it was
> built, what's left, and how to build it** — mapped to the 50-phase plan in
> `K-GPT_MASTER_PLAN_50_PHASES.md`.

---

## 1. Snapshot

**K-GPT** is a multi-tenant, account-based campus AI for KSRM College of
Engineering — a re-architecture of the single-owner TRON-X project into a
deployable product. One backend serves hundreds of isolated student accounts,
each with private chat + memory, tiered daily quotas, a paid subscription, and
an admin console.

**Stack:** FastAPI (backend) · Next.js 14 + Tailwind + Framer Motion (frontend) ·
Supabase Postgres + pgvector (data) · LiteLLM (model routing) · Razorpay (billing).

**Status at handoff**

| Stream | Phases | State |
|---|---|---|
| Milestone 1 — multi-tenant foundation | — | ✅ built & verified |
| Epic A — Foundation & Hardening | 1–6 | ◐ partial (data model + JWT/password auth done; SSO, email-verify, observability, CI/CD **pending**) |
| Epic B — Quota, Tiers & Entitlements | 7–14 | ✅ built & verified |
| Model registry (30-model catalog) | — | ✅ built & verified |
| Epic C — Billing & Subscription | 15–18 | ◐ Razorpay activate/verify done; renewals/invoices/coupons **pending** |
| Epics D–I | 19–50 | ○ not started |

---

## 2. How to run / resume

1. **Database.** Create a Supabase project. In its SQL editor run, in order:
   `supabase/schema.sql` then `supabase/migrations/002_epic_b_quota.sql`
   (both idempotent). Copy the project URL + **service-role** key.
2. **Backend.**
   ```bash
   cd backend
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env     # fill SUPABASE_*, GROQ_API_KEY, ADMIN_EMAILS, SECRET_KEY
   uvicorn app.main:app --reload --port 8400   # docs at /docs
   ```
3. **Frontend.**
   ```bash
   cd frontend
   npm install
   cp .env.example .env.local   # NEXT_PUBLIC_API_URL=http://localhost:8400
   npm run dev                   # http://localhost:3000
   ```
4. **First accounts.** Sign up with an email in `ADMIN_EMAILS` → admin (full
   access). Sign up with any `@ksrmce.ac.in` email → student, starts *inactive*
   until paid (Razorpay) or granted from the admin console.

### ⚠️ Two environment gotchas (important)
- **This dev sandbox's mounted folder truncated files on write** during the
  session (the "stale tooling" issue noted in the TRON-X case study). After
  editing any backend file here, verify with:
  `python -c "import ast; ast.parse(open('PATH').read())"`. A real deploy host
  does **not** have this problem.
- A poisoned `__pycache__` can serve stale bytecode. If imports look wrong after
  an edit, run with `PYTHONPYCACHEPREFIX=/tmp/x` or delete `__pycache__`.

---

## 3. What's DONE — and how

### 3.1 Milestone 1 — Multi-tenant foundation ✅
- **`supabase/schema.sql`** — tables (`app_users`, `chat_sessions`,
  `chat_messages`, `memory_chunks`, `usage_log`, `payments`), `pgvector`, the
  `match_memory` RPC, and **Row-Level Security** on every table (defense-in-depth;
  backend uses the service-role key and scopes by `user_id` in code).
- **Auth** (`app/routers/auth.py`, `app/core/security.py`) — JWT (HS256),
  pbkdf2 passwords, signup **gated to `@ksrmce.ac.in`** (admins exempt).
- **Chat** (`app/routers/chat.py`) — per-user sessions/messages, RAG over the
  user's own `memory_chunks`, streaming (SSE) + non-streaming.
- **Memory** (`app/routers/memory.py`, `app/services/embeddings.py`) —
  MiniLM 384-dim local embeddings; add/list/delete notes, per-user isolation.
- **Billing** (`app/routers/billing.py`) — Razorpay order → signature-verify →
  activate semester access. Falls back to admin-grant if keys absent.
- **Frontend** — landing, login/signup, streaming chat with persona switcher,
  account, admin; design system in `frontend/src/app/globals.css` +
  `tailwind.config.ts` (dark-first, glassmorphism, Framer Motion).
- **Verified:** TestClient — college-email gate 403s non-KSRM; all student/admin
  routes 401 without auth; chat/health 200.

### 3.2 Epic B — Quota, Tiers & Entitlements (Phases 7–14) ✅
The core cost-control system. **Design principle: pure policy separated from
I/O so it is unit-testable.**

- **`app/services/quota_policy.py`** — PURE functions, no DB/clock: caps
  (Normal 500k / Heavy 1M), `effective_cap = daily_cap + claimed_bonus +
  bonus_balance`, `percent_used`, `usage_state`, IST daily reset, weekly-bonus
  timing, and the auto-tiering decision. **38 unit assertions pass.**
- **`app/services/entitlements.py`** — DB-backed engine wrapping the policy:
  `refresh()` (lazy daily/weekly reset + snapshot to `usage_daily` + cap
  reconcile), `check_access()` (tier cap / sub / suspend, structured 402/429),
  `record_usage()` (atomic increment + `usage_log`), `claim_weekly_bonus()`,
  `apply_tiering()` + `run_nightly()`, and admin actions (reset/grant/set-tier/
  clear-override/refresh-bonus/suspend) — **all audit-logged to
  `entitlement_log`.**
- **`supabase/migrations/002_epic_b_quota.sql`** — adds tier/quota columns,
  `usage_daily`, `entitlement_log`, and atomic RPCs (`increment_daily_usage`,
  `bump_usage_daily`, `claim_weekly_bonus`).
- **`app/services/fairuse.py`** (Phase 14) — per-minute rate limit, concurrency
  cap, shared-login IP-anomaly detection (in-memory; swap for Redis at scale).
- **Soft limits (Phase 13)** — near-cap downshift to the cheapest tier;
  75/95% warnings surfaced in `usage_view`.
- **Percentage-only contract (Phase 12)** — student `/api/account/usage`
  returns ONLY `{percent_used, state, weekly_bonus_available, resets_in_seconds,
  warnings}`. Frontend `UsageRing.tsx` shows a % ring + state label. **No token
  integer reaches a student**; admins see raw numbers in their console only.
- **Admin controls (Phase 11)** — `app/routers/admin.py`: single + **bulk**
  (multi-select) reset/grant/set-tier/refresh-bonus/suspend, `run-nightly`
  trigger, per-user `entitlement_log` view. Frontend `admin/page.tsx` has the
  bulk action bar.
- **Scheduler (Phase 9)** — APScheduler job at 00:05 IST in `app/main.py`
  lifespan calls `entitlements.run_nightly()` (reset + auto-tiering sweep).
- **Verified:** policy 38/38, all entitlement routes gate correctly, migration
  SQL structurally complete.

### 3.3 Model registry (30-model catalog) ✅
- **`app/services/models.json`** — 11 routing categories (instant, fast_chat,
  reasoning, coding, multilingual, vision, long_context, tool_use, rag,
  background, premium), each a primary + cross-provider fallback chain;
  31-model pricing map for cost metering; 10 providers.
- **`app/services/smart_router.py`** — failover chain, per-model circuit breaker
  (3 fails → 2-min cooldown, self-heals decommissioned ids), latency tracking,
  **price-based premium gating** (students keep every cheap model incl.
  GPT-4o-mini; only >$2/1M-output models gated).
- **`app/services/intent.py`** — keyword routing; Telugu script **and** romanised
  "Tenglish" → `multilingual` (Qwen).
- **`MODELS.md`** — catalog, routing logic, and the cost math.
- **Verified:** all 11 chains build, pricing covers every routed model, gating
  correct, intent routes Telugu/Tenglish/coding correctly.

---

## 4. What's LEFT — and how to do it

Concrete guidance per remaining phase, mapped to this codebase. Format:
**objective → how (files/approach)**.

### Epic A — finish hardening (Phases 1–6)
- **P2 Auth hardening** → add `email_verified` to `app_users`; send OTP/link on
  signup (reuse TRON-X `mail_auth` pattern), block chat until verified; add
  `/api/auth/forgot` + `/reset`; rotate refresh tokens.
- **P3 College SSO** → add Google OAuth (`authlib`) with hosted-domain
  `ksrmce.ac.in`; new `app/routers/oauth.py`; link to existing `app_users`.
- **P4 Environments** → separate Supabase projects per env; gate `DEBUG`; add a
  simple feature-flag table or env list.
- **P5 Observability** → add Sentry SDK in `main.py`; structured JSON logging;
  request-id middleware. **P6 CI/CD** → GitHub Actions: ruff + pytest +
  `next build`; promote Milestone-1's smoke checks into `tests/`.

### Epic C — Billing (Phases 15–18)
- **P15 Subscription lifecycle** → add Razorpay **webhook** endpoint to
  `billing.py` (idempotent on `rzp_payment_id`); cron to expire subs past
  `sub_expires_at` + a grace window; reconcile on webhook retries.
- **P16 Plans** → a `plans` table (semester/annual; Normal vs Heavy as a paid
  add-on or free auto-upgrade); map purchase → tier/entitlements.
- **P17 Invoices/GST** → generate receipts (use the `pdf` skill); add GST fields
  to `payments`; refund endpoint that reverses access.
- **P18 Coupons/bulk** → `coupons` table + redeem endpoint; admin bulk-activate
  by roll-number list (extend `admin.py`).

### Epic D — Core chat UX (Phases 19–28) — Claude/ChatGPT/Gemini parity
- **P19 Streaming controls** → frontend `chat/page.tsx`: stop (abort the fetch
  reader), regenerate (resend last user msg), edit-and-resend, retry-with-model.
- **P20 Projects/threads** → `projects` table (user-scoped) + `project_id` on
  `chat_sessions`; sidebar grouping; full-text search over `chat_messages`.
- **P21 Model picker** → expose `models.json` categories to the client; let users
  pick a category; show the answering model (already returned as `model`).
- **P22 Rich rendering** → add KaTeX + Mermaid to the markdown renderer in
  `chat/page.tsx`; copy-code buttons (partly there).
- **P23 Artifacts/Canvas** → detect fenced HTML/React/code in replies → render in
  a split preview pane (sandboxed iframe); version history in state.
- **P24 Prompt library** → `prompts` table; `/` slash-command menu in the composer.
- **P25 Custom instructions/styles** → store in `app_users.preferences`
  (already exists); inject into the system prompt in `chat._build_messages`.
- **P26 Message actions/branch** → thumbs feedback table; edit a past message to
  fork a branch (parent-pointer on messages).
- **P27 Share links** → `shared_chats` table with a public token; read-only page;
  revoke. **P28 Command palette** → ⌘K component (new chat/persona/search/nav).

### Epic E — Knowledge, Memory & RAG (Phases 29–33)
- **P29 File upload → memory** → upload endpoint; extract with PyMuPDF/python-docx/
  python-pptx/openpyxl (already used in TRON-X); chunk → `embeddings.embed` →
  `db.insert_memory` (kind='document'); the RAG path in `chat.py` already
  searches it.
- **P30 Project knowledge** → scope `memory_chunks` by `project_id`; share across
  a project's chats. **P31 Memory v2** → the Memory browser UI (view/pin/edit/
  delete) over the existing `/api/memory` endpoints; add a memory on/off toggle.
- **P32 Citations** → return the matched `memory_chunks` ids with replies; render
  inline source chips. **P33 Web search** → add a search tool (Tavily/Brave/DDG)
  as a `tool_use` path with cited results.

### Epic F — Multimodal & Tools (Phases 34–38)
- **P34 Vision** → accept image uploads; route to the `vision` category
  (Gemini Flash / GPT-4o-mini); pass image parts to LiteLLM.
- **P35 Voice** → STT (Groq Whisper) + streaming TTS behind a VAD + confidence
  guard (fix the TRON-X silence-hallucination bug). **P36 Code interpreter** →
  reuse a sandboxed executor (resource-limited, network-off) as a tool.
- **P37 Tool/function calling** → a registry-driven tool layer; route via the
  `tool_use` category (Llama-3-Groq Tool-Use). **P38 Study aids** → generate
  flashcards/quizzes/summaries from a chat or document.

### Epic G — Trust, Safety & Compliance (Phases 39–43)
- **P39 Moderation** → input/output moderation (a fast classifier model or
  provider moderation) in the chat pre/post path. **P40 Academic integrity** →
  an **Exam/Honesty mode** system-prompt overlay, per-cohort toggle (the phase
  that answers "won't this help cheating?"). **P41 Privacy** → export-my-data +
  delete-account endpoints; retention config. **P42 Audit** → extend
  `entitlement_log` into a general admin audit trail. **P43 Injection defense** →
  treat uploaded-doc content as untrusted; harden system prompts; add a test suite.

### Epic H — Admin, Analytics & Ops (Phases 44–47)
- **P44 Admin v2** → cohort/section filters, drill-down, saved views over the
  existing admin APIs. **P45 Analytics** → dashboards from `usage_log` +
  `usage_daily` (DAU/WAU, model mix, tier distribution; raw tokens admin-only).
- **P46 Cost governance** → per-cohort budgets + alerts + auto-throttle on breach.
  **P47 Reliability** → uptime monitor, status page, backups + restore test.

### Epic I — Growth, Polish & Launch (Phases 48–50)
- **P48 Onboarding** → first-run guide, empty states, sample prompts, changelog.
- **P49 Mobile/PWA/a11y/i18n** → installable PWA, WCAG-AA, Telugu+English
  localization, performance budget. **P50 Launch** → 1-department paid pilot →
  feedback (thumbs/NPS) → staged rollout → GA.

---

## 5. Recommended next steps (critical path to a billable pilot)

Per the master plan §4, the highest-leverage order from here:

1. **P40 Academic-integrity mode** — small, and it's the question your HOD will
   ask. Do this before any pitch.
2. **P29 File upload → memory** — the single most-wanted student feature; the RAG
   backend already exists, so it's mostly extraction + an upload endpoint.
3. **P44 Admin console v2** + **P45 analytics** — needed to run and report a pilot.
4. **P2/P3 email-verify + Google SSO** — stops login-sharing (protects the budget).
5. **P15 subscription lifecycle** — reliable renewals/expiry before charging money.

Then differentiate with Epic D (P19, P22, P23, P25).

---

## 6. Key files index

| File | Role |
|---|---|
| `supabase/schema.sql`, `migrations/002_*.sql` | DB schema + Epic B migration |
| `backend/app/main.py` | App wiring, provider-key export, nightly scheduler |
| `backend/app/core/config.py` | All settings/env (incl. provider keys) |
| `backend/app/core/security.py` | JWT + password + auth dependencies |
| `backend/app/services/quota_policy.py` | PURE quota rules (unit-tested) |
| `backend/app/services/entitlements.py` | DB-backed quota engine + admin actions |
| `backend/app/services/smart_router.py` | Model failover + circuit breaker + gating |
| `backend/app/services/models.json` | Categories, pricing, providers |
| `backend/app/services/intent.py` | Category routing (Telugu/Tenglish aware) |
| `backend/app/services/fairuse.py` | Rate limit / concurrency / anomaly |
| `backend/app/routers/{auth,chat,memory,account,admin,billing,health}.py` | API |
| `frontend/src/app/{chat,account,admin,login,signup}/page.tsx` | UI surfaces |
| `frontend/src/components/UsageRing.tsx` | Percentage-only usage display |
| `K-GPT_MASTER_PLAN_50_PHASES.md` | The full roadmap + quota spec |
| `MODELS.md` | Model catalog + routing rationale |

---

## 7. Conventions & invariants (don't break these)

- **Percentage-only:** never return a raw token count to a non-admin. Student
  usage = `entitlements.usage_view()` output only.
- **Premium gating is price-based:** keep cheap models open to students; gate
  only >$2/1M-output models. Don't reintroduce provider-name drops.
- **Tenant isolation:** every query filters by `user_id`; RLS is the backstop.
  Backend uses the **service-role** key — never expose it to the frontend.
- **Quotas self-heal:** `entitlements.refresh()` runs on every request, so resets
  are correct even if the nightly job is missed. Admin tier overrides are sticky.
- **Routing self-heals:** the circuit breaker fails over from bad/decommissioned
  model ids — but verify ids against provider docs to avoid trip-and-retry latency.
- **IST everywhere** for resets (`Asia/Kolkata`).
- **Verify after editing in this sandbox** (mount truncation) — `ast.parse` check.

---

## 8. Session 2 — Epics A/C/D/E/G/H build (this session)

Continued the 50-phase plan from the Epic-B baseline. **Backend fully verified**
(58 endpoints import cleanly; 19/19 pytest pass; every file `py_compile`s).
**Frontend type-checks clean** (`tsc --noEmit`). All new code is in `K-GPT`
only; TRON-X was used purely as architectural reference and left untouched.

> ⚠️ Confirmed the documented mount gotcha: the in-IDE *file-edit* tool silently
> fails to persist edits to **existing** files here. **All edits this session were
> done via shell heredoc/`python` and verified with `grep` + `py_compile`.** New
> files written by the tool persisted fine. A real host has neither problem.

### New DB migration
- **`supabase/migrations/003_phases_d_to_i.sql`** — run after `002`. Adds:
  auth-hardening + personalization columns on `app_users` (`email_verified`,
  `exam_mode`, `response_style`, `custom_instructions`, `memory_enabled`,
  `web_search_enabled`, `plan`, `failed_logins`, `locked_until`); tables
  `auth_tokens`, `projects`, `shared_chats`, `plans`(seeded), `coupons`;
  `chat_sessions.project_id/pinned/archived`, `memory_chunks.project_id`,
  `chat_messages.parent_id/feedback`, payment GST/receipt/lifecycle fields; RLS
  on the new tenant tables. Idempotent.

### Phases delivered
- **P2 Auth hardening** — email verification + password reset (hashed,
  single-use, 24h tokens) via `services/mailer.py` (SMTP→console fallback);
  brute-force lockout; `routers/auth.py` gains `/verify`, `/resend-verification`,
  `/forgot`, `/reset`. Optional `REQUIRE_EMAIL_VERIFICATION` gate in chat.
- **P5 Observability** — `core/observability.py`: JSON request logging +
  `x-request-id` middleware; optional Sentry. Wired in `main.py`.
- **P6 CI/tests** — `backend/tests/` (`test_policy.py`, `test_api.py` w/ in-memory
  DB harness in `conftest.py`); `.github/workflows/ci.yml` (ruff + compileall +
  pytest + `next build`).
- **P15/16/17/18 Billing** — `routers/billing.py` rewritten: plans, coupons,
  GST split, receipt numbers, idempotent **webhook**, verify idempotency,
  nightly **subscription expiry** (`entitlements.expire_due_subscriptions`).
  Admin **bulk-activate by roll-number** + **coupon** create (`routers/admin.py`).
- **P19/21/22 Chat UX** — stop/regenerate/abort, model-category picker
  (`ChatReq.category`), KaTeX math + Mermaid + syntax-highlight + copy-code
  (`components/Markdown.tsx`), thumbs feedback (`/api/chat/feedback`).
- **P20/30 Projects** — `routers/projects.py` (CRUD + project knowledge);
  session `project_id`/pin/archive (`PATCH /api/chat/sessions/{id}`); message
  search (`GET /api/chat/search`).
- **P25 Custom instructions & styles** — `services/prompting.py` assembles
  persona + style + custom instructions + memory + integrity overlay; surfaced
  in `/settings`.
- **P27 Share** — `routers/share.py` + public `/s/[token]` read-only page.
- **P29 File upload → memory** — `services/extract.py` (PDF/DOCX/PPTX/XLSX/CSV/
  TXT) + chunking; `routers/upload.py` embeds into per-user (optionally
  project-scoped) pgvector memory; composer "Attach".
- **P31/32 Memory v2 + citations** — memory browser in `/settings`
  (view/delete, on/off toggle); RAG + web answers return `citations`
  (`components/Citations.tsx`).
- **P33 Web search** — `services/websearch.py` (DuckDuckGo, Tavily if keyed);
  per-message "Web" toggle; cited results.
- **P39/43 Safety** — `services/moderation.py` (self-harm/weapons/malware refusal,
  fail-soft) + prompt-injection screen/sanitise; untrusted-doc system-prompt guard.
- **P40 Academic-integrity** — exam-mode overlay (appended LAST so custom
  instructions can't override the honour code); per-user toggle in `/settings`.
- **P41 Privacy** — `GET /api/account/export`, `DELETE /api/account/delete-account`.
- **P44/45 Admin v2 + analytics** — `/api/admin/users/search` (cohort/tier/status),
  `/api/admin/analytics` (WAU, tier/sub distribution, model mix, cost — raw
  numbers admin-only).
- **P48/49 Polish** — `/settings` page, PWA manifest + viewport/theme, KaTeX/hljs
  CSS, forgot-password link, share/onboarding empty states.

### How to run the new bits
1. DB: run `supabase/migrations/003_phases_d_to_i.sql` after `002`.
2. Backend: `pip install -r backend/requirements.txt` (adds PyMuPDF, python-docx,
   python-pptx, openpyxl, sentry-sdk, pytest). New env in `backend/.env.example`
   (SMTP, SENTRY_DSN, TAVILY_API_KEY, RAZORPAY_WEBHOOK_SECRET, GST_PERCENT,
   REQUIRE_EMAIL_VERIFICATION, FRONTEND_URL).
3. Frontend: `npm install` (adds katex, remark-math, rehype-katex,
   rehype-highlight, highlight.js, mermaid), then `npm run dev`.
4. Tests: `cd backend && SECRET_KEY=x pytest -q`.

### Still open (next session)
P3 Google SSO · P4 multi-env/feature-flags · P23 Artifacts/Canvas · P24 prompt
library/slash · P26 full branch tree UI · P28 ⌘K palette · P34 vision · P35 voice ·
P36 code interpreter · P37 tool framework · P38 study aids · P46 cost governance ·
P47 reliability/status page · P50 pilot → GA. Frontend admin-v2 analytics
*dashboard* UI consumes `/api/admin/analytics` (endpoint ready; charts TODO).

---

## 9. Session 3 — remaining phases (this session)

Continued from the Session-2 baseline. **All previously-open phases delivered.**
Backend: **89 routes import cleanly · 42/42 pytest pass · ruff clean ·
compileall clean.** Frontend: **0 type errors in `src/`** (`tsc --noEmit`). All
new code is in `K-GPT` only; TRON-X was untouched (architectural reference only).

> ⚠️ Same mount gotcha as before, characterised precisely this time: the IDE
> **file-edit tool persists to the Windows FS but the Linux/bash mount keeps a
> stale cache of *existing* files** (newly-*created* files sync fine). So: **new
> files via the Write tool; edits to existing files via bash heredoc/python**,
> verified with `ast.parse` + `pytest`. `rm` on the mount is blocked (perms).

### New DB migration
- **`supabase/migrations/004_phases_remaining.sql`** — run after `003`. Adds:
  `app_users` SSO + cohort columns (`auth_provider`, `provider_sub`,
  `avatar_url`, `cohort`); tables `feature_flags`(seeded), `prompts`(seeded
  starters), `study_aids`, `cohort_budgets`, `incidents`, `feedback_responses`;
  RLS on the new per-user tables. Idempotent.

### Phases delivered
- **P3 Google SSO** — `routers/oauth.py`: verifies a Google **ID token** against
  Google tokeninfo, enforces hosted-domain `ksrmce.ac.in`, links/creates the
  user, issues our JWT. No new dependency (uses httpx). `GOOGLE_CLIENT_ID` env;
  frontend `api.googleLogin`/`googleConfig`.
- **P4 Environments & feature flags** — `services/flags.py` (cached, TTL) over a
  `feature_flags` table; admin `GET/PATCH /api/admin/flags`; `ENV` +
  `FEATURE_FLAGS_ENABLED` settings.
- **P23 Artifacts/Canvas** — `components/ArtifactPane.tsx` (`extractArtifact()`
  detects fenced html/svg/code or a full HTML doc) → sandboxed iframe split pane
  with **version history**; auto-opens on stream done + a re-open button.
- **P24 Prompt library & slash commands** — `routers/prompts.py` + seeded shared
  starters; `components/SlashMenu.tsx` shows on `/` in the composer.
- **P26 Branching** — `chat.fork_session` + `POST /api/chat/sessions/{id}/branch`;
  frontend **Edit & branch** on user messages forks an alternate session.
- **P28 Command palette** — `components/CommandPalette.tsx` (⌘K/Ctrl-K), mounted
  in chat; host-supplied actions (new chat, web toggle, voice).
- **P34 Vision** — `ChatReq.images` (data URLs); `chat._build_messages` emits
  multimodal content parts and forces the `vision` category; image attach +
  thumbnails in the composer; `smart_router` stream token-count handles list
  content.
- **P35 Voice (safe)** — `routers/voice.py`: push-to-talk clip upload → Groq
  Whisper, with a **silence floor + low-confidence/noise guard** (fixes the
  TRON-X hallucination). Gated by the `voice` flag (off by default). Frontend
  mic button via MediaRecorder + `transcribeAudio`.
- **P36 Code interpreter** — `services/sandbox.py`: subprocess `-I`, import
  denylist (socket/subprocess/…), SIGALRM timeout, RLIMIT_AS mem cap, output
  truncation. `POST /api/tools/execute` (flag-gated, rate-limited).
- **P37 Tool framework** — `services/tools.py`: registry-driven calculator
  (safe AST eval), unit convert, datetime (IST), campus info; OpenAI-style
  `SPECS`; `GET /api/tools`, `POST /api/tools/run`.
- **P38 Study aids** — `services/study.py` (flashcards/quiz/summary → strict
  JSON, metered) + `routers/study.py`; "Study" button generates from the active
  session; saved to `study_aids`.
- **P45 Analytics dashboard** — `components/AnalyticsDashboard.tsx`
  (dependency-free SVG bars + sparkline) at `/admin/analytics`, consuming the
  existing `/api/admin/analytics`. Raw tokens admin-only.
- **P46 Cost governance** — `services/cost_governance.py` (pure `evaluate_cohort`
  + `enforce` auto-throttle), per-cohort `cohort_budgets`; admin
  `GET/PUT /api/admin/budgets`, `POST /budgets/enforce`; wired into the nightly
  sweep.
- **P47 Reliability & status** — `routers/status.py`: public `GET /api/status`
  (overall + circuit-breaker degraded models + incidents) and admin incident
  CRUD; `/status` page; **`RELIABILITY.md`** runbook (uptime, drills, backups).
- **P50 Pilot toolkit** — `routers/feedback.py` (NPS/CSAT/free submit +
  admin NPS rollup); **`PILOT_RUNBOOK.md`** (pre-pilot checklist → staged
  rollout → GA gates).

### Tests added
- `tests/test_services.py` — 15 pure-logic tests (tools, sandbox, cost
  governance, study JSON extraction).
- `tests/test_features.py` — API tests (tools/sandbox, prompts, feedback/NPS
  auth, public status, google config, branch). FakeDB extended in `conftest.py`.

### How to run the new bits
1. DB: run `supabase/migrations/004_phases_remaining.sql` after `003`.
2. Backend: no new Python deps. New env in `backend/.env.example`
   (`GOOGLE_CLIENT_ID`, `ENV`, `FEATURE_FLAGS_ENABLED`).
3. Frontend: no new npm deps (native MediaRecorder/FileReader; SVG charts).
   New env `NEXT_PUBLIC_GOOGLE_CLIENT_ID`.
4. Tests: `cd backend && SECRET_KEY=x pytest -q` → 42 pass.

### Known environment note (not a code issue)
- `node_modules/@types/d3-scale/index.d.ts` is **corrupted from the original
  Windows `npm install`** (a truncated block comment → one `tsc` error outside
  `src/`). A clean `npm ci` on the deploy host fixes it; no app code references
  it directly.

### Still open / nice-to-have (next session)
- P3 SSO: render the actual Google button on `/login` (config + verify endpoint
  ready; `googleLogin` wired — just drop in the GIS `<script>` + button).
- Admin UI surfaces for feature-flag toggles, cohort budgets, and incident
  posting (endpoints + `api.ts` methods ready; charts/forms TODO).
- P26: a full branch *tree* visualiser (current impl forks to a new session).
- P36: move the sandbox into a container/gVisor for a hard security boundary
  before opening it widely.
