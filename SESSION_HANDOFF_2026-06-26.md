# K-GPT — Session Handoff (2026-06-26)

Continues `SESSION_HANDOFF_2026-06-25.md`. Covers this session's work: public
hosting on the company domain, mandatory email-OTP signup, the Razorpay-required
legal pages, KB-relevance gating, student classification (course/branch/year/sem/
section) with **auto-progressing** year/semester, admin cohort tools, and prompt
tailoring. **Faculty accounts are designed but NOT yet built — see §8 (Pending).**

> **Apply order:** run the new SQL migrations (009–012) in Supabase (and the
> Docker Postgres if self-hosting), set the new env vars, then rebuild
> (`docker compose ... up -d --build backend frontend`). Code changes need an
> image rebuild — `restart`/`up -d` alone keep the old code.

---

## 1. Public hosting on promptpulse.in (Cloudflare Tunnel)

- The app is served at **https://kgpt.promptpulse.in** via the existing Caddy +
  Cloudflare Tunnel stack. DNS moved to Cloudflare; a **named tunnel** points the
  public hostname `kgpt.promptpulse.in` → `http://caddy:8080`.
- `docker-compose.tunnel.yml` now runs the **named tunnel by default**
  (`tunnel run --token "PASTE_YOUR_CLOUDFLARE_TUNNEL_TOKEN_HERE"`); the quick
  random-URL tunnel is commented out as a fallback. Paste the real token there.
- HTTPS is automatic at Cloudflare's edge — the purchased SSL cert is **not**
  needed for this path (keep it for a future direct-origin VPS).
- Full walkthrough: `HOSTING_GUIDE_promptpulse.md`.
- **Hosting target:** runs on a PC now; CX43 (8 vCPU / 16 GB / 160 GB, ~$19/mo,
  Hetzner — prefer the **Singapore** region for India latency) is sufficient for
  launch → a few hundred students. Disable Neo4j/RabbitMQ if unused; add ~4 GB
  swap; watch Grafana and resize when RAM > 85%.

---

## 2. Mandatory email-OTP signup (NEW)

Every new non-admin user must verify a **6-digit code emailed to them** before a
session is issued. (`require_email_verification` now defaults **true**.)

- Signup creates the account but returns `otp_required` + **no token**; the UI
  shows an OTP screen (`components/OtpStep.tsx`). `/api/auth/verify-otp` checks the
  code and issues the token. `/api/auth/resend-otp` re-sends.
- Login is gated too: an unverified account is bounced to the OTP screen.
- Codes expire in `OTP_TTL_MINUTES` (default 10). Lookup is **user-scoped**
  (`db.get_auth_token_for_user`) so two users with the same code can't collide.
- Admins are auto-verified. `shristi@ksrmce.ac.in` was added as an admin (in
  `config.py` default `admin_emails`; also set `ADMIN_EMAILS` in `.env` if present).
- The OTP email + screen both tell users to **check Spam/Junk**.

### SMTP bug fixed
`mailer.send()` now uses **`SMTP_SSL` for port 465** and STARTTLS for 587 — the
prior code always did STARTTLS, which silently failed on the Zoho 465 config.

### ACTION — env (`backend/.env`)
```
FRONTEND_URL=https://kgpt.promptpulse.in   # was localhost — reset/OTP links broke
SMTP_HOST=smtppro.zoho.in
SMTP_PORT=465
SMTP_USER=<mailbox>
SMTP_PASSWORD=<app-password>               # rotate the exposed value
SMTP_FROM=<mailbox>
REQUIRE_EMAIL_VERIFICATION=true
CORS_ORIGINS=https://kgpt.promptpulse.in,http://localhost:3000   # drop trailing slash/pipe
```
Forgot-password (link-based) already existed end-to-end; it only needed the SMTP +
`FRONTEND_URL` fixes above to actually deliver mail.

---

## 3. Razorpay-required legal pages (NEW)

Razorpay verifies the site has these before issuing live keys. All are live routes,
linked from the homepage footer and each other (shared `components/LegalShell.tsx`):

`/about` · `/contact` · `/pricing` · `/privacy` · `/terms` · `/refund`

- **Before submitting to Razorpay**, fill the placeholders: real **phone** +
  **registered address** on `/contact`, effective **dates** on privacy/terms/refund,
  and jurisdiction city/state on `/terms`. Razorpay rejects placeholder text.
- Standalone styled copies also exist: `PromptPulse_KGPT_Privacy_Policy.html`,
  `PromptPulse_KGPT_Launch_Kit.html`, `PromptPulse_KGPT_Action_Plan.html`.

### Pricing & payments
- **Migration 009** sets intro pricing: **₹99/month, ₹349/semester** (GST-inclusive).
- Razorpay keys are still empty — set `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`,
  `RAZORPAY_WEBHOOK_SECRET` (complete KYC for live; Test Mode works meanwhile).
- The privacy/terms pages **promise a model-training opt-out toggle** — that toggle
  is NOT built yet (see §8).

---

## 4. Knowledge-base only answers course-relevant queries (NEW)

Two layers stop the KB firing on chit-chat / off-topic messages:

1. **Casual-message gate** (`services/smalltalk.py` `is_smalltalk`): greetings,
   thanks, byes, and identity/capability questions ("what are your capabilities
   dude") skip embedding + retrieval entirely. Strips trailing filler ("dude",
   "bro", "bhai", …) and detects meta-questions about the assistant. Strict mode is
   exempt.
2. **Relevance threshold** (`KB_RELEVANCE_THRESHOLD`, default **0.55**): shared-KB
   and personal-doc retrieval now require genuine similarity. The previous shared-KB
   path used the default 0.3 and always returned its nearest 4 chunks (the cause of
   document chips on non-educational queries). Tune lower if real course questions
   miss; higher if junk still grounds.

Strict mode itself was set to **verbatim** then reverted to **v1** (grounded,
cites sources, says "I couldn't find this in your knowledge base." when absent) —
v1 is the current behaviour.

---

## 5. Handwriting OCR for DOCX/PPTX (NEW)

`services/extract.py` `_zip_media_ocr()` now OCRs images embedded in Office files
(`word/media`, `ppt/media`) via the vision-model-first → Tesseract path, so
handwritten/scanned pictures inside a `.docx`/`.pptx` become searchable (PDFs and
image uploads already did). Needs `OCR_VISION_ENABLED=true` + a vision key
(currently `false` in `.env` — handwriting won't transcribe until enabled).

---

## 6. Student classification + auto-progressing cohort (NEW)

Students are classified by **course, branch, year, semester, section**, captured at
a **mandatory onboarding** step (`/onboarding`) gated after signup/login.

- **Year + semester auto-advance with time.** Onboarding stores the **admission
  (batch) year**; `services/cohort.py` `derive()` computes the current year +
  odd/even semester from today's date (academic year starts July; Odd ≈ Jul–Dec,
  Even ≈ Jan–Jun, clamped to course length). No manual updates ever.
- **Semester is Odd (1) / Even (2)** only — not 1–8.
- **"Other" branch** prompts a free-text "specify your branch" field.
- **Students can set their profile once (onboarding) then it's LOCKED** — the
  student preferences endpoint only accepts these fields while empty. Editing is
  **admin-only**: `PATCH /api/admin/users/{id}/profile` + an **Edit** modal on each
  admin students row. Settings shows the fields read-only with "contact admin".
- **Admin cohort filter**: the Students table has a **Class** column and filter
  dropdowns (course / branch / year / sem / section); `/users/search` accepts the
  same filters. Filter to a cohort, then use existing bulk actions to target it.
- **Branch does NOT restrict knowledge.** The shared KB is institution-wide for
  everyone; cohort is used ONLY to calibrate answer difficulty. The prompt was
  hardened so the model never refuses/narrows an answer because a topic is outside
  the student's branch.

### Migrations
- **010** year/semester/section · **011** course/branch · **012** admission_year.

---

## 7. UI tweaks

- The whole chat **composer toolbar collapses** ("Hide options" toggle) to reclaim
  space; the Strict-mode banner also has a dismiss ×.

---

## 8. PENDING — Faculty accounts (designed, NOT built)

Agreed scope ("Full faculty role"), to implement next as a focused pass:

- Add a **`faculty`** value to the `user_role` enum (`ALTER TYPE user_role ADD
  VALUE IF NOT EXISTS 'faculty'`) and a **`department`** column on `app_users`
  (the code already reads `department` in `_public`, `_admin_view`, and the admin
  edit body — column + UI still needed).
- **Student/Faculty choice at sign-up**, with a **faculty onboarding** that collects
  **Department** instead of year/sem/section.
- **Faculty are exempt** from the cohort profile (`profile_complete` for faculty =
  name + department; already stubbed in `_public`).
- **Faculty permissions:** no student daily quota; **can upload to the shared
  knowledge base** (today the "Shared KB" composer toggle and the shared-upload path
  are admin-only — extend to faculty).
- **OPEN DECISION (needs sign-off):** should faculty self-sign-up require **admin
  approval before shared-KB upload** (safer — a student could otherwise pick
  "Faculty"), or trust any `@ksrmce.ac.in` faculty sign-up? Recommend admin approval
  for the upload capability.

### Other small follow-ups noted this session
- Build the **model-training opt-out** toggle (Settings) the privacy policy promises.
- Optional: **audit log** (who/when) when an admin edits a student profile.
- Optional: cohort-**scoped** shared KB / announcements (current support = filtering
  + bulk actions on a cohort, not per-cohort visibility).
- Settings "—" (clear) on locked fields is a no-op by design (admin-only edits).

---

## 9. Key files changed / added this session

**Backend:** `services/cohort.py` (new), `services/smalltalk.py`,
`services/mailer.py`, `services/extract.py`, `services/rag.py`,
`services/prompting.py`; `routers/auth.py`, `routers/account.py`,
`routers/admin.py`, `routers/chat.py`; `schemas.py`, `core/config.py`;
`supabase/migrations/009_intro_pricing.sql`, `010_student_cohort.sql`,
`011_student_course_branch.sql`, `012_admission_year.sql`.

**Frontend:** `components/OtpStep.tsx` (new), `components/LegalShell.tsx` (new);
`app/onboarding/page.tsx` (new), `app/about|contact|pricing|privacy|terms|refund/
page.tsx` (new); `app/signup/page.tsx`, `app/login/page.tsx`, `app/chat/page.tsx`,
`app/settings/page.tsx`, `app/admin/page.tsx`, `app/page.tsx`; `lib/api.ts`.

**Infra / docs:** `docker-compose.tunnel.yml`; `HOSTING_GUIDE_promptpulse.md`,
`PromptPulse_KGPT_Action_Plan.html`, `PromptPulse_KGPT_Launch_Kit.html`,
`PromptPulse_KGPT_Privacy_Policy.html`.

---

## 10. Smoke test after deploy

1. **Signup** with a college email → OTP screen → enter code → onboarding (course,
   branch, batch year, section) → chat.
2. **Casual** "hi hello" / "what are your capabilities dude" → no document chips.
   **Course** question → grounded with citations.
3. **Strict** mode → answers only from KB, else the canned line.
4. **Admin** → filter Students by cohort; Edit a student's profile; verify locked
   fields are read-only for students.
5. **Razorpay pages** load at `/about … /refund`; **payment** once keys are set.
6. Confirm **year/semester** shown matches the batch year + current date.
