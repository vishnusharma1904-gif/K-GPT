# K-GPT — Campus AI for KSRM College of Engineering

A **multi-tenant**, account-based AI study assistant. One deployment serves
hundreds of students, each with **private chat history**, **private memory**
(RAG over their own notes), **usage quotas**, and a **paid semester
subscription**. Re-architected from the single-owner TRON-X project into a
deployable, multi-user product.

```
┌─────────────┐   REST/SSE   ┌──────────────┐   service key   ┌────────────┐
│  Next.js    │ ───────────▶ │   FastAPI     │ ──────────────▶ │  Supabase  │
│ (Fable-5 UI)│              │ multi-tenant  │                 │ Postgres + │
│  Vercel     │ ◀─────────── │  Render/VPS   │ ◀────────────── │  pgvector  │
└─────────────┘   stream     └──────────────┘                 └────────────┘
                                     │ LiteLLM
                                     ▼
                       Groq · Gemini · OpenAI · Anthropic …
```

## What's inside

| Layer | Tech | Notes |
|---|---|---|
| Frontend | Next.js 14 (App Router), Tailwind, Framer Motion, shadcn-style UI | Dark-first, glassmorphism, streaming chat |
| Backend | FastAPI (async) | Migrated SmartRouter, RAG, quota metering |
| Auth | JWT (pbkdf2 passwords) | Signup gated to `@ksrmce.ac.in` |
| Database | Supabase Postgres + **pgvector** | One DB for users, chats, memory, usage, payments |
| Isolation | `user_id` scoping + Row-Level Security | Tenant data can't leak across students |
| LLM routing | LiteLLM | Cheap-first chain, circuit breaker, failover |
| Memory | SentenceTransformers MiniLM (384-dim) | Per-user semantic search via `match_memory` RPC |
| Payments | Razorpay | ₹1000/semester; admin can also grant manually |

## Key multi-tenant features (new vs. TRON-X)

- **Real database** replacing JSON files; every row scoped by `user_id`.
- **Per-user RAG isolation** — a student's memory is searched only against their own rows.
- **Usage metering + quotas** — tokens/cost logged per request; access blocked at the cap.
- **Subscription model** — `inactive → active` on payment; expires per semester.
- **Admin dashboard** — manage students, grant/revoke access, see usage.
- **Dangerous TRON-X powers removed** for students (no system/PC/IoT/email control).

## Quick start (local)

### 1. Database
Create a project at [supabase.com](https://supabase.com), open the SQL editor,
paste **`supabase/schema.sql`**, and run it. Copy your project URL and the
**service-role** key.

### 2. Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # fill SUPABASE_*, GROQ_API_KEY, ADMIN_EMAILS, SECRET_KEY
uvicorn app.main:app --reload --port 8400
# API docs at http://localhost:8400/docs
```

### 3. Frontend
```bash
cd frontend
npm install
cp .env.example .env.local  # NEXT_PUBLIC_API_URL=http://localhost:8400
npm run dev
# App at http://localhost:3000
```

### 4. First run
- Sign up with your admin email (in `ADMIN_EMAILS`) → you get an **admin** account with access.
- Sign up with any `@ksrmce.ac.in` email → **student** account, starts *inactive*.
- Activate a student: pay via Razorpay (if configured) **or** grant from the admin dashboard.

## Deployment

See **`DEPLOYMENT.md`** for the recommended setup (Vercel + Render + Supabase)
and the single-VPS Docker option.

## License
For KSRMCE campus use. Built by Vishnu Sharma.
