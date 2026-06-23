# K-GPT — Master Implementation Plan · 50 Phases

> From the multi-tenant foundation (Milestone 1, ✅ built) to a professional,
> production-grade campus AI for KSRM College of Engineering — benchmarked
> against the product polish of **Anthropic (Claude)**, **OpenAI (ChatGPT)**,
> and **Google (Gemini)**.
>
> **Author:** Vishnu Sharma · **Scope:** full workflow, 9 epics, 50 phases.

---

## 0. How to read this plan

- **Epics (A–I)** group the 50 phases into themed streams.
- Each **Phase** has an **Objective**, **Key work**, and a **Done when** acceptance line.
- `✅` = already built in Milestone 1 · `◐` = partially built · `○` = new.
- Phases are ordered by dependency; the **Critical path** is summarised in §4.

---

## 1. Cross-cutting product principles

These hold across every phase and are non-negotiable.

1. **Privacy by tenant.** Every row is scoped by `user_id` + Row-Level Security. A bug must never leak one student's data to another.
2. **Show percentages, never raw token counts.** Anywhere usage appears — UI, emails, tooltips, admin's view *of a student* — display **"% of daily limit used"** and a **state label** (Comfortable / Getting close / Limit reached). Raw token integers appear **only** in the admin's internal analytics, never to students.
3. **Cheap-first, transparent routing.** Default to free/cheap models; surface *which* model answered, never hide it.
4. **Fail soft.** Hitting a limit yields a calm, helpful state with a clear next step (wait for reset / claim weekly bonus / contact admin) — never a raw error.
5. **Inspectable & reversible.** Memory is editable; quotas are resettable by admin; every admin action is audit-logged.
6. **Accessible & fast.** WCAG-AA, keyboard-first, sub-second first paint, mobile-equal.

---

## 2. The Quota & Entitlements System (detailed spec)

This is the backbone of cost control and the core of this request. It replaces
the simple semester token bucket from Milestone 1.

### 2.1 Tiers (assigned by usage statistics)

| Tier | Daily cap | Who gets it |
|---|---|---|
| **Normal** (paid) | **500,000 tokens/day** | Default for every paid student. |
| **Heavy hitter** (paid) | **1,000,000 tokens/day** | Auto-assigned to consistently high-usage students (see §2.4), or set by admin. |

> Caps are **daily**, on a rolling reset (§2.3). The tier only changes the size
> of the daily bucket — both are paid; "heavy hitter" is a usage classification,
> not a separate purchase, unless you later decide to price it.

### 2.2 Weekly bonus

- Every paid student has a **100,000-token weekly bonus**, usable **once per 7-day window**.
- The student **claims** it (one tap) — typically when they've hit the daily cap and need a bit more that day. Claiming adds 100,000 tokens to **today's** available budget.
- Resets every 7 days (per-user `weekly_bonus_reset_at`). Unused bonus does **not** roll over.

### 2.3 Reset logic

- **Daily**: `daily_used` resets to 0 at **00:00 IST** (configurable), via a scheduled job + a lazy check on each request (whichever comes first), so resets are correct even if a job is missed.
- **Weekly bonus**: `weekly_bonus_available` flips back to `true` 7 days after the user's anchor day.
- **Admin grants** (§2.5) live in a separate `bonus_balance` bucket that is **consumed only after** the daily cap is exhausted and is **not** wiped by the daily reset.

### 2.4 Usage-statistics tiering (auto promote / demote)

A nightly job evaluates each paid student's rolling stats and assigns a tier:

- **Promote to Heavy** when, over the last **7 days**, the student hit ≥80% of the Normal daily cap on **≥4 days** (i.e. a sustained heavy user), OR claimed the weekly bonus and still capped out.
- **Demote to Normal** when 14-day usage stays below 40% of the Normal cap.
- **Admin override is sticky**: if an admin manually sets a tier, auto-tiering skips that user until the admin clears the override.
- All transitions are logged and (optionally) emailed: "You've been upgraded to a higher daily limit."

### 2.5 Admin entitlement controls

From the admin console, for any selected user (or a multi-select cohort):

- **Reset daily usage** — set `daily_used = 0` immediately (e.g. a student needs more today).
- **Grant extra tokens** — add N tokens to `bonus_balance` (persists across daily resets until used).
- **Set tier** — force Normal / Heavy with a sticky override.
- **Refresh weekly bonus** — re-arm the 100k bonus early.
- **Suspend / restore** — pause access without deleting the account.

### 2.6 Data model additions (`app_users` + new tables)

```
app_users (+):
  tier                text     default 'normal'      -- normal | heavy
  tier_override       boolean  default false          -- admin set, skips auto-tiering
  daily_cap           bigint   default 500000         -- derived from tier
  daily_used          bigint   default 0
  daily_reset_at      timestamptz                     -- next reset
  weekly_bonus_available boolean default true
  weekly_bonus_reset_at  timestamptz
  bonus_balance       bigint   default 0              -- admin grants, persistent

usage_daily (rollups for tiering + analytics):
  user_id, day (date), tokens, requests, hit_cap boolean

entitlement_log (audit of every grant/reset/tier change):
  id, actor_user_id, target_user_id, action, delta, reason, created_at
```

### 2.7 The percentage-only display contract

- Student-facing usage is **always** `round(used / effective_cap * 100)` where
  `effective_cap = daily_cap + claimed_bonus_today + bonus_balance`.
- UI shows a ring/bar with the **%** and a label:
  `0–74% → "Comfortable"`, `75–94% → "Getting close"`, `95–99% → "Almost at today's limit"`, `100% → "Daily limit reached"`.
- At 100%: offer **"Use weekly bonus"** (if available) or **"Resets in Xh Ym"**.
- **No endpoint** returns raw token counts to a non-admin client. The student `/usage` API returns only `{percent_used, state, bonus_available, resets_in_seconds}`.

---

## 3. The 50 Phases

### Epic A — Foundation & Hardening (Phases 1–6)

**Phase 1 — Multi-tenant data model & RLS** ◐
- *Objective:* lock in tenant isolation as the bedrock.
- *Key work:* finalize Supabase schema, Row-Level Security on every table, service-role-only backend, migration scripts (Alembic-style ordering).
- *Done when:* an automated test proves user A can never read user B's sessions, messages, memory, or usage.

**Phase 2 — Auth hardening** ◐
- *Objective:* production-grade accounts.
- *Key work:* email verification on signup, password reset flow, refresh-token rotation, device/session list with revoke, brute-force lockout.
- *Done when:* unverified accounts can't chat; users can reset passwords and revoke sessions.

**Phase 3 — College SSO (Google Workspace)** ○
- *Objective:* one-tap login with the college Google account; kills password sharing.
- *Key work:* Google OAuth (hosted-domain `ksrmce.ac.in` restriction), Microsoft optional, account linking.
- *Done when:* students log in with their college Google account; non-domain accounts are rejected.

**Phase 4 — Environments & config** ○
- *Objective:* safe dev → staging → prod separation.
- *Key work:* per-env secrets, separate Supabase projects/keys, feature flags, `ENV`-gated debug.
- *Done when:* a change can be shipped to staging and promoted to prod without manual edits.

**Phase 5 — Observability** ○
- *Objective:* see what's happening in production.
- *Key work:* structured JSON logging, Sentry error tracking, request IDs/tracing, latency + error dashboards.
- *Done when:* every error is captured with context; p50/p95 latency is visible.

**Phase 6 — CI/CD & tests** ○
- *Objective:* ship safely and often.
- *Key work:* GitHub Actions (lint, type-check, pytest, `next build`), preview deploys, smoke tests, rollback runbook.
- *Done when:* merges auto-deploy to staging green-gated by tests.

### Epic B — Quota, Tiers & Entitlements (Phases 7–14) — *core of this plan*

**Phase 7 — Usage metering pipeline v2** ✅ *(built)*
- *Objective:* accurate, async, never-lost token accounting.
- *Key work:* exact prompt/completion token capture per request (incl. streaming), write to `usage_log` + increment `daily_used` atomically, nightly rollup into `usage_daily`.
- *Done when:* logged tokens reconcile with provider dashboards within ~2%.

**Phase 8 — Daily quota engine (500k / 1M)** ✅ *(built)*
- *Objective:* enforce the tiered daily caps with rolling reset.
- *Key work:* `effective_cap = daily_cap + claimed_bonus + bonus_balance`; pre-request check; lazy + scheduled 00:00 IST reset; graceful 100% state.
- *Done when:* a Normal user is blocked past 500k/day, a Heavy user past 1M/day, and both reset correctly.

**Phase 9 — Usage-statistics auto-tiering** ✅ *(built)*
- *Objective:* classify Normal vs Heavy from real behaviour (§2.4).
- *Key work:* nightly job over `usage_daily`, promote/demote rules, sticky admin override, transition logging + optional email.
- *Done when:* a sustained heavy user is auto-promoted to 1M/day; a light user is demoted; admin overrides stick.

**Phase 10 — Weekly bonus (100k, once/week)** ✅ *(built)*
- *Objective:* the claimable weekly top-up.
- *Key work:* `weekly_bonus_available` flag, claim endpoint (adds 100k to today), 7-day per-user reset, "claim" CTA at the cap.
- *Done when:* a capped student can claim +100k once per week and not again until reset.

**Phase 11 — Admin entitlement controls** ✅ *(built)*
- *Objective:* reset / grant / re-tier selected users or cohorts (§2.5).
- *Key work:* reset daily usage, grant tokens to `bonus_balance`, set tier, refresh weekly bonus, suspend/restore; multi-select bulk actions; every action → `entitlement_log`.
- *Done when:* admin can pick one or many users and reset or grant in one action, fully audited.

**Phase 12 — Percentage-only usage UX** ✅ *(built)*
- *Objective:* enforce the "no token counts" contract (§2.7).
- *Key work:* `/usage` returns only `{percent_used, state, bonus_available, resets_in}`; ring/bar UI with state labels; remove every raw count from student views.
- *Done when:* no student-facing surface shows a token integer; QA audit passes.

**Phase 13 — Soft limits & graceful degradation** ✅ *(built)*
- *Objective:* warn early, degrade kindly.
- *Key work:* 75% / 95% nudges, auto-downshift to cheaper models near the cap, queued-not-failed at 100% with reset countdown.
- *Done when:* approaching the cap is a smooth experience, not a wall.

**Phase 14 — Fair-use & abuse guardrails** ✅ *(built)*
- *Objective:* stop one account serving ten people / runaway cost.
- *Key work:* per-minute rate limits, concurrent-session caps, shared-login/device-fingerprint anomaly detection, automatic temporary throttle + admin alert.
- *Done when:* credential-sharing and abnormal spikes are detected and throttled automatically.

### Epic C — Billing & Subscription (Phases 15–18)

**Phase 15 — Subscription lifecycle** ◐
- *Objective:* robust paid-access state machine.
- *Key work:* Razorpay order→verify→activate (built), renewals, expiry, grace period, webhook reconciliation, idempotency.
- *Done when:* paid access activates, renews, and expires reliably even on webhook retries.

**Phase 16 — Plans & pricing** ○
- *Objective:* clean plan definitions.
- *Key work:* semester (₹1000) and annual options; map Heavy tier as either auto (free upgrade) or a priced add-on (your call); proration.
- *Done when:* a student can pick and pay for a plan; entitlements follow automatically.

**Phase 17 — Invoices, receipts, GST, refunds** ○
- *Objective:* finance-grade records.
- *Key work:* generated invoices/receipts, GST fields, refund flow, billing history page.
- *Done when:* every payment has a downloadable receipt; refunds reverse access.

**Phase 18 — Coupons, referrals & bulk licensing** ○
- *Objective:* growth + institutional deals.
- *Key work:* coupon codes, referral credits, department/section bulk activation by roll-number list.
- *Done when:* admin can bulk-activate a class; students can redeem codes.

### Epic D — Core Chat Experience (Phases 19–28) — *Claude / ChatGPT / Gemini parity*

**Phase 19 — Streaming UX polish** ◐
- *Objective:* a chat that feels like the frontier apps.
- *Key work:* stop generation, regenerate, continue, edit-and-resend, retry-with-different-model.
- *Done when:* every control works mid-stream without losing the thread. *(Inspired by: ChatGPT/Claude.)*

**Phase 20 — Conversation management & Projects** ○
- *Objective:* organize work, not just chat.
- *Key work:* rename, pin, archive, full-text search; **Projects/folders** grouping threads + shared context. *(Claude Projects, ChatGPT Projects.)*
- *Done when:* a student can group a semester's chats into a Project and search across them.

**Phase 21 — Model picker & routing transparency** ◐
- *Objective:* show and let users choose the brain.
- *Key work:* model selector with capability badges (fast / reasoning / coding), display the model that answered, "thinking" indicator for reasoning models. *(Gemini model picker, Claude model badges.)*
- *Done when:* users can pick a category and always see which model replied.

**Phase 22 — Rich rendering** ◐
- *Objective:* publication-quality output.
- *Key work:* markdown, syntax-highlighted code with copy button, **KaTeX math**, tables, Mermaid diagrams.
- *Done when:* code, math, and tables render perfectly and are copyable.

**Phase 23 — Artifacts / Canvas** ○
- *Objective:* live side-panel for generated code/docs.
- *Key work:* render HTML/React/code previews and editable documents in a split "Artifact" pane; version history. *(Claude Artifacts, OpenAI Canvas, Gemini Canvas.)*
- *Done when:* asking for a webpage or doc opens a live, editable preview beside the chat.

**Phase 24 — Prompt library & slash commands** ○
- *Objective:* reusable, fast prompting.
- *Key work:* saved prompts, `/` slash commands, starter templates (essay, code review, exam Qs).
- *Done when:* students insert saved prompts and trigger commands with `/`.

**Phase 25 — Custom instructions & response styles** ○
- *Objective:* personalization like the big three.
- *Key work:* per-user "about me / how to respond" custom instructions; selectable response **styles** (concise, detailed, formal). *(ChatGPT Custom Instructions, Claude Styles.)*
- *Done when:* custom instructions persist and visibly shape replies.

**Phase 26 — Message actions & branching** ○
- *Objective:* control over the conversation tree.
- *Key work:* copy, thumbs up/down feedback, edit a past message to **branch** an alternate path, view branches.
- *Done when:* editing an earlier turn forks a new branch without losing the original.

**Phase 27 — Shareable conversation links** ○
- *Objective:* share knowledge safely.
- *Key work:* read-only public share links with redaction controls; revoke anytime. *(ChatGPT/Claude share.)*
- *Done when:* a student can publish a read-only link and revoke it.

**Phase 28 — Command palette & shortcuts** ◐
- *Objective:* keyboard-first speed.
- *Key work:* ⌘K palette (new chat, switch persona/project, search, settings), full shortcut map.
- *Done when:* power users can drive the whole app from the keyboard.

### Epic E — Knowledge, Memory & RAG (Phases 29–33)

**Phase 29 — File & image upload → memory** ○
- *Objective:* chat over your own material.
- *Key work:* upload PDF/docx/pptx/xlsx/images → extract → chunk → embed into per-user pgvector memory; attachment-scoped Q&A. *(ChatGPT file upload, Claude PDF.)*
- *Done when:* a student uploads lecture notes and asks questions grounded in them.

**Phase 30 — Projects with shared knowledge** ○
- *Objective:* a knowledge base per course.
- *Key work:* Project-level document sets shared across that Project's chats; per-Project instructions.
- *Done when:* documents added to a Project are available to every chat in it.

**Phase 31 — Long-term memory v2 (transparent + editable)** ◐
- *Objective:* an AI that remembers you, that you control.
- *Key work:* auto-extracted durable facts, a Memory browser to view/pin/edit/delete, memory on/off toggle. *(ChatGPT Memory, Claude memory.)*
- *Done when:* students can see and curate exactly what K-GPT remembers.

**Phase 32 — Citations & source grounding** ○
- *Objective:* trustworthy answers.
- *Key work:* when RAG is used, cite the source chunk/file inline; click to view the passage.
- *Done when:* memory-grounded answers show their sources.

**Phase 33 — Web search grounding** ○
- *Objective:* current, cited information.
- *Key work:* optional web search tool with inline citations and a sources list. *(Gemini grounding, ChatGPT search.)*
- *Done when:* enabling search yields answers with verifiable citations.

### Epic F — Multimodal & Tools (Phases 34–38)

**Phase 34 — Vision** ○
- *Objective:* understand images and diagrams.
- *Key work:* image input to vision-capable models, screenshot/diagram/handwriting understanding.
- *Done when:* a student photographs a problem and gets a worked solution.

**Phase 35 — Voice mode (safe re-introduction)** ○
- *Objective:* talk to K-GPT — the TRON-X feature, done right.
- *Key work:* STT + streaming TTS behind a VAD + confidence guard (no silence hallucinations); push-to-talk first.
- *Done when:* voice works reliably with no phantom input on silence.

**Phase 36 — Code interpreter / sandbox** ○
- *Objective:* run code safely for learning.
- *Key work:* sandboxed Python execution (resource-limited, network-off), show output/plots; per-user isolation. *(ChatGPT Code Interpreter.)*
- *Done when:* students run snippets and see results without risk to the host.

**Phase 37 — Tool / function-calling framework** ○
- *Objective:* extensible capabilities.
- *Key work:* structured tool-calling layer (calculator, unit convert, citation lookup, campus info), registry-driven so tools are pluggable.
- *Done when:* the model can call registered tools and compose results.

**Phase 38 — Study-aid generation** ○
- *Objective:* turn answers into artifacts students keep.
- *Key work:* generate flashcards, summaries, practice tests, charts/diagrams from a chat or a document.
- *Done when:* one click turns notes into a quiz or summary.

### Epic G — Trust, Safety & Compliance (Phases 39–43)

**Phase 39 — Content moderation & safety** ○
- *Objective:* keep the platform safe and on-mission.
- *Key work:* input/output moderation, category filters, age-appropriate guardrails, safe-completion fallbacks.
- *Done when:* disallowed content is blocked with a helpful message, logged for review.

**Phase 40 — Academic-integrity guardrails** ○
- *Objective:* a tool that helps students learn, not cheat — the question your HOD will ask.
- *Key work:* an **Exam/Honesty mode** (explains, won't hand full graded-assignment answers), configurable per cohort, honor-code prompts.
- *Done when:* the college can enable an integrity policy that K-GPT enforces.

**Phase 41 — Privacy & data rights** ○
- *Objective:* student data control.
- *Key work:* export my data, delete my account + data, retention windows, consent for memory/training-off by default. *(GDPR/DPDP-aligned.)*
- *Done when:* a student can export and delete everything; defaults are privacy-safe.

**Phase 42 — Audit logging & accountability** ◐
- *Objective:* who did what, provably.
- *Key work:* `entitlement_log` + admin-action audit trail, immutable logs, access reviews. *(SOC2-style.)*
- *Done when:* every admin grant/reset/suspend is traceable to an actor and time.

**Phase 43 — Abuse & prompt-injection defense** ○
- *Objective:* resist jailbreaks and injected instructions.
- *Key work:* system-prompt hardening, untrusted-content sandboxing (uploaded docs can't issue commands), injection test suite.
- *Done when:* a red-team prompt-injection suite passes.

### Epic H — Admin, Analytics & Operations (Phases 44–47)

**Phase 44 — Admin console v2** ◐
- *Objective:* run the whole service from one place.
- *Key work:* cohort/section views, search/filter, bulk entitlement actions, user drill-down (usage as %, not tokens), suspend/restore.
- *Done when:* admin manages thousands of students efficiently with bulk actions.

**Phase 45 — Analytics dashboards** ○
- *Objective:* understand usage, retention, cost.
- *Key work:* DAU/WAU, retention cohorts, model mix, tier distribution, peak-load charts — **raw tokens visible here (admin-only)**.
- *Done when:* you can see adoption and cost trends at a glance for the pilot report.

**Phase 46 — Cost governance** ○
- *Objective:* never get a surprise bill.
- *Key work:* per-cohort budgets, spend alerts, automatic global throttle on budget breach, provider cost reconciliation.
- *Done when:* spend is capped and alerts fire before budgets are exceeded.

**Phase 47 — Reliability & incident response** ○
- *Objective:* a service students can depend on at exam time.
- *Key work:* uptime monitoring, status page, on-call/alerting, provider-outage failover drills, backups + restore test.
- *Done when:* outages are detected, communicated, and recovered per a runbook.

### Epic I — Growth, Polish & Launch (Phases 48–50)

**Phase 48 — Onboarding & in-app guidance** ○
- *Objective:* time-to-first-value in under a minute.
- *Key work:* guided first-run, empty states, sample prompts, changelog/"what's new", tooltips.
- *Done when:* a new student sends a useful first message without help.

**Phase 49 — Mobile/PWA, accessibility, i18n, performance** ◐
- *Objective:* equal experience everywhere, for everyone.
- *Key work:* installable PWA, WCAG-AA, **Telugu + English** localization, Core-Web-Vitals budget, offline-friendly shell.
- *Done when:* the app is installable, accessible, bilingual, and fast on a mid-range phone.

**Phase 50 — Pilot → feedback → general availability** ○
- *Objective:* launch across KSRMCE the right way.
- *Key work:* 1-department paid pilot → instrument feedback (thumbs, NPS, surveys) → fix → staged rollout to all sections → GA.
- *Done when:* K-GPT is live for the college with a measured adoption and satisfaction baseline.

---

## 4. Critical path & suggested sequencing

The fastest route to a **billable, safe pilot**, then to a polished product:

```
Billable-pilot-ready (do first):
  1 → 2 → 7 → 8 → 10 → 11 → 12 → 15 → 40 → 44
  (isolation, auth, metering, daily caps, weekly bonus, admin grant/reset,
   %-only UX, subscriptions, academic-integrity mode, admin console)

Then differentiation (Claude/ChatGPT/Gemini parity):
  19 → 20 → 22 → 23 → 25 → 29 → 31 → 33

Then trust + scale + launch:
  39 → 41 → 42 → 45 → 46 → 47 → 48 → 49 → 50

Parallelizable any time: 3 (SSO), 5 (observability), 6 (CI/CD), 28 (palette).
```

**Recommended first slice (≈ 2–3 focused weeks):** Phases 7–12 + 40 + 44 — this
delivers the exact quota system you specified (tiered daily caps, usage-based
tiering, weekly bonus, admin reset/grant, %-only display) plus the integrity
mode and admin tooling needed to defend the pilot to your HOD.

---

## 5. Professional-features matrix (what we borrow, and from whom)

| Capability | Anthropic (Claude) | OpenAI (ChatGPT) | Google (Gemini) | K-GPT phase |
|---|---|---|---|---|
| Artifacts / live canvas | Artifacts | Canvas | Canvas | 23 |
| Projects + shared knowledge | Projects | Projects | Gems | 20, 30 |
| Long-term memory (editable) | Memory | Memory | — | 31 |
| Custom instructions / styles | Styles | Custom Instructions | — | 25 |
| File / PDF / image upload | PDF + vision | File upload | Multimodal | 29, 34 |
| Web search w/ citations | Web search | Search | Grounding | 33 |
| Code interpreter sandbox | — | Code Interpreter | — | 36 |
| Tool / function calling | Tools | Tools | Function calling | 37 |
| Voice mode | — | Advanced Voice | Live | 35 |
| Shareable chats | Share | Share | Share | 27 |
| Model picker + transparency | Model badges | Model picker | Model picker | 21 |
| Stop/regenerate/edit/branch | ✓ | ✓ | ✓ | 19, 26 |
| Usage transparency (as %) | Limits UI | Limits UI | Limits UI | 12 |

---

*Quota rules in §2 are the authoritative spec; phases 7–14 implement them.
Display percentages only — never token counts — to all non-admin users.*
