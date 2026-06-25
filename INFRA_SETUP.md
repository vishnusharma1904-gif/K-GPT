# K-GPT — Self-Hosted Infrastructure: Setup & Why

This covers the five backing services K-GPT can run on: **PostgreSQL, Redis,
Qdrant, RabbitMQ, and Neo4j**. For each one: what it's for, what K-GPT actually
uses it for, and how to set it up.

> **Important — these are optional.** K-GPT runs perfectly fine *without* any of
> them on the "lightweight" profile (Supabase + Groq + Fireworks). Every client
> degrades gracefully: leave the env var blank and that feature falls back or
> turns off. You only need these five when you want to **self-host** (own your
> data) and **scale** (hundreds of concurrent users). The fastest way to get all
> five is `docker compose up` — they're already defined in `docker-compose.yml`.

---

## TL;DR — bring everything up

```bash
# 1. From the repo root, create a .env with strong passwords (used by compose):
cat > .env <<'EOF'
POSTGRES_PASSWORD=<strong-random>
REDIS_PASSWORD=<strong-random>
QDRANT_API_KEY=<strong-random>
RABBITMQ_PASSWORD=<strong-random>
NEO4J_PASSWORD=<strong-random>
GRAFANA_PASSWORD=<strong-random>
EOF

# 2. Start just the infrastructure (not the app) to set it up first:
docker compose up -d postgres redis qdrant rabbitmq neo4j

# 3. Check they're healthy:
docker compose ps
```

Then put the matching connection strings in `backend/.env` (see each section
below), and start the app with `docker compose up --build` (or run the backend
locally pointing at these containers).

Generate a strong value with: `python -c "import secrets;print(secrets.token_urlsafe(32))"`

---

## 1. PostgreSQL — the system of record

**What it is:** a relational (SQL) database. K-GPT uses the `pgvector/pgvector:pg16`
image, which is Postgres 16 with the `pgvector` extension baked in.

**Why K-GPT uses it:** it's the self-hosted replacement for managed Supabase —
full control over extensions and connection pooling, no row/bandwidth limits, no
vendor lock-in. It holds the structured, transactional data: user accounts,
chat sessions and messages, quotas/usage, billing, and the `documents` table the
background worker updates as it processes uploads. With `pgvector` it can also
store embedding vectors (`memory_chunks`) as the fallback retrieval path when
Qdrant isn't configured.

> Note: today most routers still talk to Supabase (`supabase_client.py`); the
> self-hosted `postgres_client.py` path is wired into the worker and is the
> migration target. So in the current build, Postgres is primarily the worker's
> document-status store.

**Connection (in `backend/.env`):**
```
DATABASE_URL=postgresql+asyncpg://pp_admin:<POSTGRES_PASSWORD>@localhost:5432/promptpulse
DATABASE_URL_SYNC=postgresql://pp_admin:<POSTGRES_PASSWORD>@localhost:5432/promptpulse
```

**Setup options:**
- **Docker (recommended):** already in compose. On first boot it auto-runs
  `deployment/postgres/init.sql`. Then load the full app schema:
  `psql "$DATABASE_URL_SYNC" -f supabase/setup_all.sql` and the files in
  `supabase/migrations/` (including the new `008_qwen768_shared_kb.sql`).
- **Standalone container:**
  ```bash
  docker run -d --name kgpt-pg -p 5432:5432 \
    -e POSTGRES_DB=promptpulse -e POSTGRES_USER=pp_admin \
    -e POSTGRES_PASSWORD=<pw> -v pg_data:/var/lib/postgresql/data \
    pgvector/pgvector:pg16
  ```
- **Managed alternative:** Supabase, Neon, or AWS RDS (must support `pgvector`).

**Verify:** `psql "$DATABASE_URL_SYNC" -c "select version();"`

---

## 2. Redis — cache + shared state

**What it is:** an in-memory key-value store (extremely fast, data lives in RAM
with optional disk persistence).

**Why K-GPT uses it:** it's the shared "scratchpad" that multiple backend
replicas need so they don't each keep their own divergent copy. Concretely,
`redis_client.py` uses it for **six** things:

1. **Embedding cache** — skip re-embedding text we've already seen.
2. **Semantic response cache** — identical/near-identical questions return a
   stored answer with zero LLM cost.
3. **Rate limiting** — per-user per-minute counters (`fairuse`).
4. **Circuit-breaker state** — which model providers are currently "tripped"
   (`smart_router`), shared across replicas.
5. **Concurrency guard** — caps simultaneous in-flight requests per user.
6. **Scheduler leader lock** — ensures the nightly cron runs on exactly one
   worker (the fix added this session).

**Connection:**
```
REDIS_URL=redis://:<REDIS_PASSWORD>@localhost:6379/0
```

**Setup options:**
- **Docker:** in compose (`redis:7-alpine`, 512 MB, LRU eviction, AOF persistence).
- **Standalone:** `docker run -d --name kgpt-redis -p 6379:6379 redis:7-alpine redis-server --requirepass <pw>`
- **Managed alternative:** Upstash (has a free tier) or Redis Cloud.

**Verify:** `redis-cli -a <pw> ping` → `PONG`

---

## 3. Qdrant — the vector database (RAG engine)

**What it is:** a purpose-built database for **vector similarity search** — you
store embeddings and ask "find the chunks most semantically similar to this
query."

**Why K-GPT uses it:** this is the heart of retrieval (RAG). It holds the
embedded document chunks, per-user memory facts, the **shared institutional
knowledge base**, and the semantic-cache vectors. It replaces `pgvector` at
scale: it uses HNSW indexing (sub-50 ms search at ~1M vectors, no blocking index
rebuilds) and supports payload filtering by `user_id` / `project_id` / `shared`.
Without Qdrant, retrieval falls back to the slower `pgvector` path.

**Connection:**
```
QDRANT_HOST=localhost
QDRANT_PORT=6333            # ← an int; do NOT leave this blank
QDRANT_API_KEY=<QDRANT_API_KEY>
```

**Setup options:**
- **Docker:** in compose (`qdrant/qdrant:v1.12.5`, REST 6333 / gRPC 6334).
- **Standalone:** `docker run -d --name kgpt-qdrant -p 6333:6333 -p 6334:6334 -e QDRANT__SERVICE__API_KEY=<key> -v qdrant_data:/qdrant/storage qdrant/qdrant:v1.12.5`
- **Managed alternative:** Qdrant Cloud (free tier available).

**Collections are created automatically** by `qdrant_client.ensure_collections()`
when the backend/worker starts — no manual schema step.

**Verify:** open `http://localhost:6333/dashboard` or `curl http://localhost:6333/healthz`

---

## 4. RabbitMQ — the background job queue

**What it is:** a message broker. Producers drop tasks onto durable queues;
worker processes pull them off and run them — decoupled and crash-safe.

**Why K-GPT uses it:** to move heavy work off the request path so the user isn't
left waiting and nothing is lost on restart. `queue_client.py` publishes and the
`worker.py` process consumes three queues:

1. **Document pipeline** — parse → chunk → embed → store in Qdrant.
2. **Memory extraction** — pull durable facts from a user's messages.
3. **Knowledge-graph updates** — e.g. mastery analysis feeding Neo4j.

Without RabbitMQ these fall back to in-process best-effort tasks (which are lost
if the server restarts), so it's what makes ingestion reliable at scale.

**Connection:**
```
RABBITMQ_URL=amqp://pp_rabbit:<RABBITMQ_PASSWORD>@localhost:5672/
```

**Setup options:**
- **Docker:** in compose (`rabbitmq:3-management-alpine`). Management UI at
  `http://localhost:15672` (user `pp_rabbit`).
- **Standalone:** `docker run -d --name kgpt-rabbit -p 5672:5672 -p 15672:15672 -e RABBITMQ_DEFAULT_USER=pp_rabbit -e RABBITMQ_DEFAULT_PASS=<pw> rabbitmq:3-management-alpine`
- **Managed alternative:** CloudAMQP (free tier).

**Queues are declared automatically** by `queue_client.ensure_queues()` at
startup. **Verify:** log into the management UI and watch the queues.

---

## 5. Neo4j — the knowledge graph

**What it is:** a graph database — it stores *nodes* and *relationships* and is
built to traverse connections that are painful to model in SQL joins.

**Why K-GPT uses it:** to represent how learning fits together —
`Student —ENROLLED_IN→ Course`, `Concept —DEPENDS_ON→ Concept`,
`Student —MASTERED→ Concept`. `knowledge_graph.py` writes mastery analysis here,
and it powers the "what should this student learn next?" recommendation,
prerequisite checking, and cross-course concept linking. It's the most optional
of the five — if `NEO4J_URI` is blank, the graph features simply don't run.

**Connection:**
```
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=<NEO4J_PASSWORD>
```

**Setup options:**
- **Docker:** in compose (`neo4j:5-community`). Browser UI at
  `http://localhost:7474` (user `neo4j`). Seed data lives in
  `deployment/neo4j/init.cypher` — run it once:
  `cypher-shell -u neo4j -p <pw> -f deployment/neo4j/init.cypher`
- **Standalone:** `docker run -d --name kgpt-neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/<pw> neo4j:5-community`
- **Managed alternative:** Neo4j Aura (free tier).

**Verify:** open `http://localhost:7474`, log in, run `RETURN 1;`

---

## Putting it together

| Service | Port(s) | Env var(s) | If left blank… |
|---|---|---|---|
| PostgreSQL | 5432 | `DATABASE_URL`, `DATABASE_URL_SYNC` | uses Supabase instead |
| Redis | 6379 | `REDIS_URL` | caching/rate-limit fall back to in-process |
| Qdrant | 6333 / 6334 | `QDRANT_HOST`, `QDRANT_PORT`, `QDRANT_API_KEY` | retrieval falls back to pgvector |
| RabbitMQ | 5672 / 15672 | `RABBITMQ_URL` | background jobs run in-process (lost on restart) |
| Neo4j | 7474 / 7687 | `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` | graph/recommendation features off |

**Recommended order to stand up:**
1. Set passwords in the root `.env`, run `docker compose up -d postgres redis qdrant rabbitmq neo4j`.
2. Wait for `docker compose ps` to show all healthy.
3. Load the Postgres schema; run the Neo4j seed cypher.
4. Fill the connection strings into `backend/.env`.
5. Start backend + worker (`docker compose up --build`, or run locally).
6. On startup, Qdrant collections and RabbitMQ queues auto-create; check
   `GET /api/health` for a green report.

**Note on the scheduler:** the compose file sets `RUN_SCHEDULER=1` on the worker,
but the nightly cron now elects its single runner automatically via the Redis
leader lock (added this session). With `REDIS_URL` set, you don't need to manage
that flag — `RUN_SCHEDULER` is effectively a no-op and can be removed.

**Security:** every service in compose is bound to `127.0.0.1` only, so nothing is
exposed to the internet. Keep it that way in production and reach them over the
Docker network or an SSH tunnel — never publish 5432/6379/etc. publicly.
