# K-GPT — Session Handoff (2026-06-24)

This document captures everything changed in this working session, how to run the
app locally, the database migrations you must apply, known limitations, and the
prioritized backlog. Hand this to the next developer (or future-you).

---

## 1. What this session delivered

### A. Stabilization — fixed breaking bugs from the "Prompt Pulse" migration
The migration to self-hosted infra (Postgres/Redis/Qdrant/RabbitMQ/Neo4j) and
API-based embeddings had shipped several runtime-breaking issues. All fixed:

- **`smart_router` calls** in `memory_extractor.py` and `knowledge_graph.py` called a
  non-existent `chat_completion`. Switched to `smart_router.complete(...)`, fixed
  response parsing (`response["text"]`) and model ids. Added a `response_format`
  passthrough to `complete()` for JSON mode.
- **Billing config** — `semester_fee_inr` and `gst_percent` were removed from
  `config.py` but still referenced by `billing.py`. Restored them.
- **`MONTHLY_DAILY_CAP`** — referenced by `quota_policy.cap_for_tier` but deleted.
  Restored the constant.
- **`entitlements.record_usage`** — removed the "thinking out loud" Redis code and
  the off-by-one bug; added a clean `redis_client.incr_by(...)` helper.
- **`smart_router.health()`** — no longer reads dead in-memory circuit state; reads
  tripped circuits from Redis (`redis_client.list_open_circuits()`).
- **Startup hardening** — `main.py` lifespan and `qdrant_client.ensure_collections()`
  now swallow connection errors, so a configured-but-down service (running the API
  without the full Docker stack) **cannot crash startup**.
- **Worker** — removed dummy-text fabrication; a missing source file now fails the
  document instead of ingesting placeholder text.

### B. RAG cutover + token/LLM-load efficiency
- New `app/services/rag.py`: **Qdrant-first retrieval** (dense search + cross-encoder
  rerank) with **pgvector fallback** when Qdrant isn't configured.
- **Semantic response cache** — near-identical generic questions are answered from
  Qdrant's `pp_semantic_cache` with **zero LLM tokens** (gated to non-personalized
  requests so it can never leak one user's context to another).
- **Token efficiency** — conversation history is trimmed to a char budget
  (`HISTORY_CHAR_BUDGET`), retrieval context is capped (top-4 docs / top-3 memory,
  700-char snippets), and embeddings are Redis-cached.
- Uploads are routed to Qdrant when configured (pgvector otherwise).

### C. Embeddings + reranker on Qwen via Fireworks
- Embeddings: **`accounts/fireworks/models/qwen3-embedding-8b`**, requested at
  **768 dimensions** via the `dimensions` param (Matryoshka). 768 keeps vectors
  compatible with the Qdrant collections and the pgvector schema, and stays under
  pgvector's 2000-dim index limit.
- Reranker: **`accounts/fireworks/models/qwen3-reranker-8b`** (`/v1/rerank`), with
  response parsing that accepts either `results` or `data` keys.

### D. Shared institutional knowledge base (the "admin-verified documents" feature)
- **Admin uploads** a document marked shared/verified → stored institution-wide
  (not scoped to one user). Regular users' uploads stay private.
- **Retrieval checks the shared KB first** for every user, ranked at the top of the
  context as `[VERIFIED · filename]`, so answers are grounded in admin docs before
  the model reasons on its own.
- **Admin UI**: a "Shared KB" toggle in the chat composer, plus a managed panel at
  **`/admin/knowledge`** (upload / list / delete shared documents).
- Backend: `/api/upload` accepts a `shared` flag (admin-only, 403 for students);
  `/api/admin/knowledge` GET/DELETE; data-layer functions in both `supabase_client`
  and `qdrant_client`.

### E. UX + quality fixes
- **Attachment chip** in the input bar (spinner → "ready · N chunks"), replacing the
  plain text status line.
- **Math rendering** — system prompt now instructs LaTeX output (`$…$` / `$$…$$`);
  `Markdown.tsx` also normalizes `\(…\)` / `\[…\]` to `$` so KaTeX always renders.
- **Anti-hallucination grounding** — the system prompt no longer tells the model it
  "remembers past conversations." Added an explicit rule: never fabricate shared
  history, projects, or that a user uploaded a doc; only use facts present in context.
- **Upload size limit** raised 15 MB → **50 MB** (`extract.py`).
- Created `backend/.env.example` (full template) and `frontend/.env.local`.
- Fixed `Dockerfile` (removed the obsolete sentence-transformers pre-download that
  broke `docker build`).
- Pinned `starlette==0.41.3` in `requirements.txt` (FastAPI 0.115.5 needs <0.42).

---

## 2. Database migrations to apply (Supabase SQL editor)

Run these **in order**. All are idempotent / safe to re-run.

### 2.1 Move the vector store to 768 dimensions (Qwen embeddings)
```sql
drop index if exists idx_memory_embedding;
alter table memory_chunks drop column if exists embedding;
alter table memory_chunks add column embedding vector(768);
create index idx_memory_embedding on memory_chunks
  using ivfflat (embedding vector_cosine_ops) with (lists = 100);

drop function if exists match_memory(uuid, vector, int, float);
create function match_memory(
  p_user_id uuid, p_query vector(768),
  p_limit int default 6, p_min_sim float default 0.40
) returns table (id uuid, content text, source text, similarity float)
language sql stable as $$
  select m.id, m.content, m.source, 1 - (m.embedding <=> p_query) as similarity
  from memory_chunks m
  where m.user_id = p_user_id and m.embedding is not null
    and 1 - (m.embedding <=> p_query) >= p_min_sim
  order by m.embedding <=> p_query limit p_limit;
$$;
```

### 2.2 Shared knowledge base columns + search function
```sql
alter table memory_chunks add column if not exists shared   boolean not null default false;
alter table memory_chunks add column if not exists verified boolean not null default false;

create or replace function match_shared_memory(
  p_query vector(768), p_limit int default 6, p_min_sim float default 0.40
) returns table (id uuid, content text, source text, similarity float)
language sql stable as $$
  select m.id, m.content, m.source, 1 - (m.embedding <=> p_query) as similarity
  from memory_chunks m
  where m.shared = true and m.embedding is not null
    and 1 - (m.embedding <=> p_query) >= p_min_sim
  order by m.embedding <=> p_query limit p_limit;
$$;
```

### 2.3 Reload PostgREST cache (always after DDL)
```sql
notify pgrst, 'reload schema';
```

> Note: also ensure the full base schema is loaded — run `supabase/setup_all.sql`
> (not just `schema.sql`) so all auth/quota columns exist.

---

## 3. Running locally

### Backend
```powershell
cd D:\K-GPT\backend
python -m venv .venv            # use Python 3.11
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8400
```
Verify: http://127.0.0.1:8400/docs and http://127.0.0.1:8400/api/health

### Frontend
```powershell
cd D:\K-GPT\frontend
npm install
npm run dev                     # http://localhost:3000
```

### Environment notes (gotchas hit this session)
- **`CORS_ORIGINS`** must include the exact frontend origin (e.g.
  `http://localhost:3000`) or the browser blocks requests with a 400 on the
  preflight. For ngrok, the frontend URL, the API URL it calls, and CORS must all
  match.
- **Optional infra** — leave `DATABASE_URL`, `REDIS_URL`, `QDRANT_HOST`,
  `RABBITMQ_URL`, `NEO4J_URI` blank to run lightweight on Supabase + Groq +
  Fireworks. They degrade gracefully. **Do not blank `QDRANT_PORT`** (it's an int).
- **`FIREWORKS_API_KEY`** is required for embeddings + reranking (RAG). Without it,
  embeddings return zero vectors and retrieval is effectively off.
- **`GOOGLE_CLIENT_ID`** is needed for Google sign-in (else use email/password;
  sign up first at `/signup`).
- Data layer is **still Supabase** (the routers use `supabase_client`); the
  self-hosted Postgres path (`postgres_client.py`) exists but isn't wired into the
  routers yet.

### Full stack (production-like)
`docker compose up --build` brings up postgres, redis, qdrant, rabbitmq, neo4j,
backend, worker, frontend, prometheus, grafana. Fill `backend/.env` first.

---

## 4. Demo flow (admin shared-KB document Q&A)
1. Log in as **admin** (email in `ADMIN_EMAILS`; sign up first if needed).
2. Upload a subject PDF via the **"Shared KB"** toggle in chat, or **/admin/knowledge**.
3. Log in as a **fresh student account** (empty profile → no confabulation).
4. Ask a question about the document → grounded answer, cited as a `knowledge`
   source, math rendered as LaTeX.

---

## 5. Known limitations / caveats
- **Handwriting / scanned PDFs not supported.** Extraction reads only the digital
  text layer (`page.get_text()`); scanned/handwritten files have none. Needs OCR
  (Tesseract) + a vision model — see backlog.
- **`MAX_CHUNKS = 120`** (`upload.py`) caps how much of a large file is indexed.
- **Sequential embedding** — each chunk embeds via a separate Fireworks call; large
  uploads are slow. Batch the embedding requests as a future optimization.
- **Nightly scheduler double-fire** — `uvicorn --workers 2` runs the APScheduler
  lifespan in both workers. Gate it behind a single-instance flag before production.
- **Shared KB applies when the asking user has memory enabled** (the default). Users
  who disabled personal memory won't trigger retrieval; decouple shared retrieval
  from the personal-memory toggle if needed.
- **Verification caveat for this session:** the agent's sandbox served truncated
  copies of files edited this session, so the full test suite couldn't be run there.
  Pure-logic modules were verified against the authoritative source and pass. Run
  `cd backend && python -m pytest -q` on a real machine to confirm green.

---

## 6. Backlog (agreed: build after the demo)
1. **Image extraction + display** from shared docs (extract → store → serve → render
   a figure gallery under grounded answers).
2. **Download answers as PDF** (client-side print-to-PDF first: math, tables,
   images; later a polished server-side export).
3. **Auto graphs/charts** — model emits chart specs/data → render to image → inline
   + embed in PDFs.
4. **OCR + handwriting recognition** for uploads (Tesseract for print, vision model
   for handwriting).

---

## 7. Key files changed/added this session
**Backend:** `app/services/rag.py` (new), `embeddings.py`, `reranker.py`,
`memory_extractor.py`, `knowledge_graph.py`, `smart_router.py`, `entitlements.py`,
`quota_policy.py`, `prompting.py`, `worker.py`, `extract.py`;
`app/db/redis_client.py`, `qdrant_client.py`, `supabase_client.py`;
`app/routers/chat.py`, `upload.py`, `admin.py`, `main.py`, `health.py`;
`core/config.py`; `requirements.txt`; `.env.example`; `Dockerfile`.
**Frontend:** `src/app/chat/page.tsx`, `src/app/admin/page.tsx`,
`src/app/admin/knowledge/page.tsx` (new), `src/components/Markdown.tsx`,
`src/lib/api.ts`, `.env.local` (new).
