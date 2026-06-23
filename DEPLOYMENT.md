# K-GPT Deployment Guide

## Option A — Managed (recommended, lowest ops)

**Database → Supabase** · **Backend → Render/Railway** · **Frontend → Vercel**

### 1. Supabase
1. Create a project. Note the **Project URL** and **service-role key** (Settings → API).
2. SQL editor → paste `supabase/schema.sql` → Run. This creates all tables,
   `pgvector`, the `match_memory` RPC, RLS policies, and triggers.

### 2. Backend on Render
- New **Web Service** from your repo, root `backend/`.
- Build: `pip install -r requirements.txt`
- Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Env vars: copy everything from `backend/.env.example`. Must set:
  `SECRET_KEY` (run `python -c "import secrets;print(secrets.token_hex(32))"`),
  `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `GROQ_API_KEY`, `ADMIN_EMAILS`,
  `CORS_ORIGINS` (your Vercel URL), `ENV=production`, `DEBUG=false`.
- First boot downloads the embedding model (~90 MB) — give it a moment.

### 3. Frontend on Vercel
- Import repo, root `frontend/`.
- Env var: `NEXT_PUBLIC_API_URL=https://<your-render-backend>.onrender.com`
- Deploy. Vercel auto-detects Next.js.

### 4. Razorpay (optional, for self-serve payments)
- Create a Razorpay account → API keys (start in **Test mode**).
- Set `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` on the backend.
- Without these, payments are disabled and you grant access from the admin panel
  (good for the first pilot where the department collects fees offline).

## Option B — Single VPS (cheapest at scale)

```bash
git clone <repo> && cd K-GPT
cp backend/.env.example backend/.env   # fill it in
docker compose up -d --build
# backend :8400, frontend :3000 — put nginx/Caddy in front for TLS
```
Still uses Supabase for the database. To self-host Postgres instead, point
`SUPABASE_URL` at your own instance with the REST layer, or swap the data layer
in `app/db/supabase_client.py` for SQLAlchemy (left as a future step).

## Security checklist (before going live)
- [ ] `SECRET_KEY` is a strong 32-byte random value, not the default.
- [ ] `ENV=production`, `DEBUG=false`.
- [ ] `CORS_ORIGINS` is your exact frontend domain, not `*`.
- [ ] `SUPABASE_SERVICE_KEY` is set only on the backend, never in the frontend.
- [ ] `PREMIUM_MODELS_FOR_STUDENTS=false` so students can't run up GPT-4 costs.
- [ ] Confirm signup is gated to `@ksrmce.ac.in` (test with a gmail address → should 403).
- [ ] Quotas set sensibly (`DEFAULT_QUOTA_TOKENS`) for your per-student budget.

## Cost control
- Default routing prefers **free/cheap** models (Groq, Gemini Flash).
- Every request is logged to `usage_log` with token counts and estimated cost.
- Per-student `quota_tokens` hard-caps spend; raise/lower per cohort from the admin API.
- Watch `/api/admin/stats` for total tokens used across all students.

## Scaling notes
- Backend is stateless → scale horizontally (more Render instances / compose replicas).
- pgvector `ivfflat` index handles per-user search well into tens of thousands of chunks.
- Move the embedding model to a dedicated worker if CPU becomes the bottleneck.
