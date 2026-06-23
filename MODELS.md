# K-GPT Model Registry & Routing

K-GPT routes every request to the cheapest model that fits, with automatic
failover. Costs are USD per 1M tokens (in/out). Config lives in
`backend/app/services/models.json`; logic in `smart_router.py`.

## How routing works
1. **Intent → category** (`intent.py`): keyword/script detection picks a category
   without an extra LLM call. Telugu script *and* romanised "Tenglish" route to
   **multilingual** (Qwen).
2. **Category → chain** (`models.json`): each category has a primary + ordered
   fallbacks across providers.
3. **SmartRouter** drops models whose provider key is missing, skips any model
   whose circuit breaker is open (3 consecutive failures → 2-min cooldown), and
   tries the chain in order. A decommissioned/unavailable id self-heals via
   failover — so the catalog can be generous.
4. **Cost metering**: the chosen model's price (from the pricing map) is logged
   per request and counts against the student's daily quota.
5. **Premium gating**: students get every cheap model (incl. GPT-4o-mini, Gemini
   Flash). Only models with output price > $2/1M (e.g. Claude) are gated behind
   the opt-in premium toggle.

## Categories
| Category | Primary | When used |
|---|---|---|
| `instant` | Llama 3.1 8B (Groq) | short turns, near-cap downshift |
| `fast_chat` | Llama 3.3 70B (Groq) | default balanced chat |
| `reasoning` | DeepSeek V4 | math/logic/STEM |
| `coding` | DeepSeek Coder | code gen/debug |
| `multilingual` | Qwen 2.5 72B | Telugu / Tenglish / mixed |
| `vision` | Gemini Flash | images/diagrams |
| `long_context` | Gemini Flash (1M) | big PDFs/codebases |
| `tool_use` | Llama-3-Groq Tool-Use | function calling (Phase 37) |
| `rag` | Command R | cited answers over docs |
| `background` | Nemotron Mini 4B | titles/intent/summaries |
| `premium` | GPT-4o-mini | opt-in best, cost-controlled |

## Cost model (why this stays profitable)
Default chat runs on Groq Llama / Gemma and Gemini Flash at **$0.05–0.79 / 1M**.
A heavy student doing ~1.8M tokens/month costs roughly **$0.40–1.50/month** —
well under the per-semester fee. Premium (Claude) is gated; pricey models never
run for a student unless they opt in and the admin allows it.

## The 30-model catalog (sourced)
Grouped by provider family; all reachable via native APIs or one OpenRouter key.

**Chinese titans:** DeepSeek V4 (0.30/0.50), DeepSeek Coder (0.14/0.28),
MiniMax M3 (0.30/1.20), Kimi K2 (0.40/1.20), Qwen 2.5/3 MoE (0.29/0.59),
Qwen 2.5 7B (0.05/0.08), Yi-Lightning (0.14/0.28), GLM-4-Flash (0.10/0.30).

**Mistral MoE:** Mixtral 8x7B (0.20/0.20), Mixtral 8x22B (0.50/0.50),
Mistral NeMo 12B (0.15/0.15), Ministral 8B (0.10/0.10), Codestral (0.30/0.90).

**NVIDIA NIM:** Nemotron Mini 4B (0.03/0.03), Llama 3.1 Nemotron 70B (0.59/0.79),
NeMo-Minitron 8B (0.10/0.10).

**Llama/Gemma (Groq/Fireworks):** Llama 3.1 8B (0.05/0.08),
Llama 3.3 70B (0.59/0.79), Llama-3-Groq Tool-Use (0.05/0.08),
Gemma 2 9B (0.06/0.06), Gemma 2 27B (0.20/0.20).

**Enterprise MoE:** Jamba 1.5 Mini (0.20/0.40), DBRX (0.60/0.60),
Snowflake Arctic (0.60/0.60), WizardLM-2 8x22B (0.50/0.50), Command R (0.50/1.50).

**Big-tech Flash:** Gemini Flash-Lite (0.10/0.40), Gemini Flash (0.50/1.50),
GPT-4o-mini (0.15/0.60).

> Model ids in `models.json` use LiteLLM's provider-prefixed format. Verify exact
> ids against each provider's current docs before production — the SmartRouter
> will fail over from any that have been renamed/retired, but a correct primary
> avoids the first-call latency of a trip-and-retry.
