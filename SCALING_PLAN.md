# K-GPT — Scaling & Capacity Plan (50 → 500 → 1000 users)

Goal: serve more users at **95%+ uptime** without tripping provider API
concurrency/rate limits. Good news: your `smart_router` already does the hard
part (multi-provider failover + circuit breaker). The work is mostly (a) a
global concurrency limiter, (b) shared state when you run >1 server, and (c)
spreading load across providers — *legitimately*.

---

## TL;DR

1. **The limit is concurrency, not total users.** 1000 registered users is maybe
   30–60 *simultaneous* requests at peak. That's small — if you spread it.
2. **Don't create fake accounts/keys to dodge limits.** It violates provider ToS
   and gets keys banned, which *lowers* your uptime. Use multiple **providers**
   (you already do) + paid tiers + a queue.
3. **Buy the API (pay-as-you-go RPM/TPM) tier, not the individual "Token Plan."**
   The Token Plan's 3–7 concurrent-agent cap will throttle a multi-user app.
4. Add a **per-provider concurrency semaphore + 429 backoff + Redis** and you're
   set through 1000 users for well under ~$300/mo of model spend.

---

## 1. The real constraint: concurrency, not headcount

An LLM request holds a provider "slot" for the few seconds it streams. What
matters is how many are **in flight at once**, not how many accounts exist.

Rule of thumb for a campus tool: peak concurrent requests ≈ **3–6%** of total
users. Each request occupies a provider for ~3–15s.

| Users | Active/day | Peak concurrent | Msgs/month (≈) | Tokens/month (≈2.5K/msg) |
|------:|-----------:|----------------:|---------------:|--------------------------:|
| 50    | ~30        | **2–4**         | ~9,000         | ~25M                      |
| 500   | ~300       | **10–30**       | ~90,000        | ~225M                     |
| 1000  | ~600       | **25–60**       | ~180,000       | ~450M                     |

Even at 1000 users, ~60 concurrent calls spread over 4–5 providers is ~12 each —
far below any paid tier's burst ceiling (e.g., MiniMax paid bursts to ~500 RPM).
**Token volume is cheap; concurrency is the thing to engineer.**

---

## 2. About "multiple accounts / multiple keys"

Honest answer: **don't multi-account to bypass per-account limits.** MiniMax,
OpenAI, Anthropic, Groq, etc. all prohibit it in their ToS, they detect it
(same payment method / IP / fingerprint), and the penalty is suspension of the
keys — i.e., an outage during your busiest moment. That directly fights your
95% uptime goal.

What's legitimate and achieves the *same* throughput:

- **Multiple providers**, each with its own key and its own limit, in a failover
  chain. This is real horizontal capacity and you already have the machinery.
- **One paid account per provider on the right tier**, and **request a rate-limit
  increase** when you need more (every major provider grants these for real apps).
- Separate keys per **environment** (dev/staging/prod) or per **workload** — fine
  and encouraged; that's not evasion.
- A **queue + backoff** so bursts wait a moment instead of erroring.

---

## 3. Provider strategy — your biggest lever (already half-built)

Your `smart_router` routes by category with automatic failover and a per-model
circuit breaker. Lean into it:

- **Spread the default load across cheap, fast providers:** Groq (very fast),
  Fireworks AI (hosts MiniMax M3/M2.7, DeepSeek, Qwen, Kimi, GLM, GPT-OSS),
  Gemini, DeepSeek, Mistral. Each provider = an independent concurrency budget.
- **OpenRouter as overflow / catch-all** — it itself spreads across providers,
  great for absorbing spikes.
- **Keep students on cheap models** (your premium gating already does this) so
  the bulk of traffic hits the providers with the most generous limits.
- **MiniMax** is best consumed as **one provider in the pool** (you already reach
  MiniMax M3 via Fireworks), not as the sole backend.

The single most important addition: a **global per-provider concurrency cap** so
you queue locally before a provider would 429 you (see §8).

---

## 4. What to do at each phase

### Phase 1 — 50 users (today)
- **One** backend instance is plenty (your in-memory `fairuse`/circuit-breaker is fine).
- 1–2 providers with keys (Groq + Fireworks). No infra changes.
- Host: a single managed container (Render/Railway/Fly) with health checks +
  auto-restart. Frontend on Vercel/Netlify (CDN).
- Action items: set a strong `SECRET_KEY`, `ENV=production`, real `CORS_ORIGINS`,
  enable the `/status` page, turn on Sentry.

### Phase 2 — 500 users (~10–30 concurrent)
- Add the **global per-provider semaphore + 429 retry/backoff** (§8). This alone
  prevents almost all limit errors.
- Run **2 backend replicas** behind the platform's load balancer (JWT = stateless,
  so this just works) — but now move shared state to **Redis** (next point).
- **Redis** for `fairuse` rate/concurrency counters and the circuit-breaker state
  (your code comments already flag this). Without it, 2 instances each allow the
  full per-user limit.
- Run the **APScheduler nightly job on ONE instance only** (gate with an env var
  like `RUN_SCHEDULER=1`) so replicas don't double-run resets.
- Add a **response cache** (exact-match first, semantic later) — campus apps have
  huge repeat-question overlap; this cuts provider load and cost dramatically.
- Turn on **Supabase connection pooling (Supavisor/pgbouncer)**.

### Phase 3 — 1000 users (~25–60 concurrent)
- **3–4 replicas** with autoscaling on CPU/req latency; Redis shared state.
- Move **embeddings off the request path**: the in-process `sentence-transformers`
  model competes for CPU. Either a dedicated embedding worker/queue or a hosted
  embedding API. Pre-compute upload embeddings in a background job.
- **Semantic cache** (embed the question, reuse answers to near-duplicates).
- Optional but powerful: **self-host one open model on vLLM** (e.g., a Llama/Qwen)
  for your baseline "instant/fast" category — removes provider limits for the
  bulk of traffic; keep hosted providers for burst + premium.
- Provider rate-limit increases on your top 2–3 providers.
- Add a lightweight **request queue** (so a spike of 80 waits ~1–2s rather than 429).

---

## 5. Uptime: what 95% / 99% / 99.9% actually take

- **95%** = ~36 h downtime/month. A single managed instance with auto-restart +
  health checks technically clears this — but one crash can eat hours, so it's
  fragile. Treat 95% as the floor, not the target.
- **99%** (~7 h/mo) = **2+ replicas** behind a load balancer + **managed Postgres**
  (Supabase) + health checks. This is the right aim and not much extra work.
- **99.9%** (~43 min/mo) = multi-AZ, managed Redis/DB with failover, zero-downtime
  deploys, real on-call + alerting.

For all tiers: **fail soft.** Your circuit breaker + multi-provider failover means
one provider outage shouldn't take you down — make sure every category has at
least two providers with keys. Keep the `/status` page and Sentry alerts live.

---

## 6. MiniMax plans — what to buy (and what to avoid)

From the pricing you're looking at:

- **Individual "Token Plan" (Plus $20 / Max $50 / Ultra $120)** — these are
  capped to **3–4 / 4–5 / 6–7 concurrent agents** and count **every tool call as
  a request**. The token *volume* is huge (Max ≈ 5.1B/mo would cover even 1000
  users' ~450M), but the **concurrency cap makes them unsuitable as the backend
  for a multi-user app.** Great for one power user; wrong shape for a SaaS.
- **What to use instead:** the **developer API (pay-as-you-go, RPM/TPM tiers)**.
  Paid tiers go to ~100k+ requests/day and burst ~500 RPM — plenty for 1000
  users — and you can request increases. Or simply keep reaching **MiniMax models
  through Fireworks** (already in your router), letting Fireworks handle scaling.
- **Net:** treat MiniMax as one strong model option inside your provider pool,
  billed via API/Fireworks — not via an individual token subscription.

---

## 7. Cost ballpark (model spend only)

Using cheap/open models (~$0.2–0.6 per 1M tokens), which your gating favors:

- 50 users (~25M tok): **~$5–15/mo**
- 500 users (~225M tok): **~$45–135/mo**
- 1000 users (~450M tok): **~$90–270/mo**

Add hosting: ~$20–60/mo (Phase 1–2 managed containers) up to ~$150–400/mo at
Phase 3 (replicas + Redis + maybe a vLLM GPU box). Caching can cut model spend
30–60% for a campus Q&A pattern.

---

## 8. Concrete code changes (in priority order)

1. **Global per-provider concurrency limiter** in `smart_router` — an
   `asyncio.Semaphore` per provider (sized to your tier's safe concurrency), so
   calls queue locally instead of getting 429'd. *(Biggest reliability win.)*
2. **429 / rate-limit retry with exponential backoff + jitter** before failing
   over (LiteLLM supports `num_retries`); your circuit breaker handles hard-down.
3. **Redis-back** `fairuse` counters + circuit-breaker state once you run >1
   instance (your code already notes this).
4. **Scheduler-on-one-instance** guard (`RUN_SCHEDULER` env) so replicas don't
   double-run the nightly sweep.
5. **Response cache** (start with exact-match keyed on normalized prompt+persona+
   model; add semantic later).
6. **Embeddings off the hot path** (background job for uploads; consider hosted
   embeddings at Phase 3).
7. **Supabase pooling** + sensible per-tier `fairuse` limits.
8. Ensure **every routing category has ≥2 providers with keys** so failover always
   has somewhere to go.

I can implement #1, #2, and #4 now if you want — they're small, high-impact, and
don't change your UX.

---

## Sources
- [MiniMax — Rate Limits (docs)](https://platform.minimax.io/docs/guides/rate-limits)
- [MiniMax — Token Plan](https://platform.minimax.io/subscribe/token-plan)
- [MiniMax API pricing: tokens & concurrency (Flowith)](https://flowith.io/blog/minimax-api-pricing-tokens-concurrency/)
- [MiniMax agentic workflow request limits (BSWEN)](https://docs.bswen.com/blog/2026-04-25-minimax-agentic-workflow-request-limits/)
