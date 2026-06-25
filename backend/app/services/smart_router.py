"""K-GPT SmartRouter — cheap-first multi-provider routing with failover.

  * category-based model selection (see models.json)
  * provider drop when the API key is missing
  * automatic failover across the fallback chain
  * per-model circuit breaker (trip after N consecutive failures)
  * rolling P50 latency tracking
  * token + cost accounting for metering
  * price-based premium gating (students keep all cheap models)

LiteLLM gives one API across every provider; exotic models route via OpenRouter.
"""
from __future__ import annotations

import json
import os
import re
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, AsyncIterator

import litellm

litellm.suppress_debug_info = True
litellm.drop_params = True  # silently drop unsupported params per provider

_CATALOG = json.loads((Path(__file__).parent / "models.json").read_text())
_PRICING = _CATALOG["pricing_per_1m"]
_PROVIDER_ENV = _CATALOG["provider_env"]

# --- circuit breaker state ---------------------------------------------------
# Trip counts stay process-local (a few stray failures per replica is fine), but
# the OPEN/CLOSED decision lives in Redis so every replica shares one view.
_fail_counts: dict[str, int] = defaultdict(int)
_latency: dict[str, deque] = defaultdict(lambda: deque(maxlen=20))

_TRIP_AFTER = 3
_OPEN_SECONDS = 120
_PREMIUM_OUT_THRESHOLD = 2.0  # USD / 1M output tokens → gated behind premium

# ZenMux is an OpenAI-compatible gateway. Catalog ids of the form
# `zenmux/<vendor>/<model>` are sent to its endpoint via litellm's openai
# provider with a custom api_base, unlocking ZenMux's cheap/free model lineup
# through a single key.
_ZENMUX_BASE = "https://zenmux.ai/api/v1"


def _is_zenmux(model: str) -> bool:
    return model.startswith("zenmux/")


def _litellm_target(model: str) -> tuple[str, dict]:
    """Map a catalog model id to (litellm_model, extra_kwargs)."""
    if _is_zenmux(model):
        slug = model[len("zenmux/"):]
        return f"openai/{slug}", {"api_base": _ZENMUX_BASE, "api_key": os.getenv("ZENMUX_API_KEY", "")}
    return model, {}


# Providers a paid/admin user may explicitly pick from (Phase 21 model picker).
SELECTABLE_PROVIDERS = {"groq", "gemini", "mistral", "fireworks_ai", "openrouter", "zenmux"}

_PRETTY_PROVIDER = {
    "groq": "Groq", "gemini": "Google Gemini", "mistral": "Mistral",
    "fireworks_ai": "Fireworks AI", "openrouter": "OpenRouter", "zenmux": "ZenMux",
}


_LABEL_OVERRIDES = {
    "fireworks_ai/accounts/fireworks/models/kimi-k2p7-code": "Kimi K2.7 Code",
    "fireworks_ai/accounts/fireworks/models/minimax-m3": "MiniMax M3",
    "fireworks_ai/accounts/fireworks/models/qwen3p7-plus": "Qwen3.7 Plus",
    "fireworks_ai/accounts/fireworks/models/deepseek-v4-pro": "DeepSeek V4 Pro",
    "fireworks_ai/accounts/fireworks/models/kimi-k2p6": "Kimi K2.6",
    "fireworks_ai/accounts/fireworks/models/minimax-m2p7": "MiniMax M2.7",
    "fireworks_ai/accounts/fireworks/models/qwen3p6-plus": "Qwen3.6 Plus",
    "fireworks_ai/accounts/fireworks/models/glm-5p1": "GLM 5.1",
    "fireworks_ai/accounts/fireworks/models/gpt-oss-120b": "GPT-OSS 120B",
    "fireworks_ai/accounts/fireworks/models/gpt-oss-20b": "GPT-OSS 20B",
    "fireworks_ai/accounts/fireworks/models/nemotron-3-ultra-nvfp4": "Nemotron 3 Ultra",
    "fireworks_ai/accounts/fireworks/models/deepseek-v4-flash": "DeepSeek V4 Flash",
}


def _label_for(model: str) -> str:
    """A short, human-friendly model name from a litellm id."""
    if model in _LABEL_OVERRIDES:
        return _LABEL_OVERRIDES[model]
    tail = model.split("/")[-1]
    return tail.replace("-", " ").replace("_", " ").title()


def selectable_models() -> list[dict]:
    """Concrete models a paid user can pin, limited to SELECTABLE_PROVIDERS."""
    out = []
    for mid, px in _PRICING.items():
        prov = _provider_of(mid)
        if prov not in SELECTABLE_PROVIDERS:
            continue
        out.append({
            "id": mid,
            "label": _label_for(mid),
            "provider": prov,
            "provider_label": _PRETTY_PROVIDER.get(prov, prov),
            "price_out": px.get("out", 0.5),
            "available": _has_key(mid),
            "frontier": is_frontier(mid),
            "multiplier": cost_multiplier(mid),
        })
    out.sort(key=lambda m: (m["provider_label"], m["price_out"]))
    return out


def _explicit_chain(model: str) -> list[str]:
    """Chain for an explicitly chosen model, with one safe fallback."""
    candidates = [model, "groq/llama-3.3-70b-versatile"]
    chain = [m for m in candidates if _has_key(m) and not _circuit_open(m)]
    return chain or [model]


def _provider_of(model: str) -> str:
    return model.split("/", 1)[0]


def _has_key(model: str) -> bool:
    env = _PROVIDER_ENV.get(_provider_of(model))
    return bool(os.getenv(env)) if env else True


from app.db import redis_client

def _circuit_open(model: str) -> bool:
    return redis_client.circuit_is_open(model)


def _record_fail(model: str) -> None:
    _fail_counts[model] += 1
    if _fail_counts[model] >= _TRIP_AFTER:
        redis_client.circuit_trip(model, _OPEN_SECONDS)


def _record_ok(model: str, dt: float) -> None:
    _fail_counts[model] = 0
    _latency[model].append(dt)


def _cost(model: str, p_tok: int, c_tok: int) -> float:
    px = _PRICING.get(model, {"in": 0.5, "out": 0.5})
    return round(p_tok / 1e6 * px["in"] + c_tok / 1e6 * px["out"], 6)


def _is_premium_priced(model: str) -> bool:
    return _PRICING.get(model, {"out": 0.5})["out"] > _PREMIUM_OUT_THRESHOLD


# Frontier models (>40B params OR in+out price > $1) burn the daily cap faster.
_FRONTIER_MULTIPLIER = 3.5
_FRONTIER_KEYWORDS = ("ultra", "opus", "405b", "-max")


def _params_billions(model: str) -> float:
    """Best-effort parameter size (in billions) parsed from a model id."""
    tail = model.lower()
    best = 0.0
    for a, b in re.findall(r"(\d+)x(\d+)b", tail):      # e.g. 8x22b -> 176
        best = max(best, int(a) * int(b))
    for n in re.findall(r"(?<![x\d])(\d+)b", tail):       # e.g. 70b -> 70
        best = max(best, float(n))
    return best


def is_frontier(model: str) -> bool:
    px = _PRICING.get(model, {"in": 0.5, "out": 0.5})
    if (px.get("in", 0) + px.get("out", 0)) > 1.0:
        return True
    if _params_billions(model) > 40:
        return True
    return any(k in model.lower() for k in _FRONTIER_KEYWORDS)


# Per-model multiplier overrides (win over the frontier default).
_MULTIPLIER_OVERRIDES = {
    "groq/llama-3.3-70b-versatile": 1.5,   # capable but cheap — bill 1.5x, not 3.5x
}


def cost_multiplier(model: str) -> float:
    """How fast this model drains the daily cap. Overrides win; else frontier 3.5x, else 1x."""
    if model in _MULTIPLIER_OVERRIDES:
        return _MULTIPLIER_OVERRIDES[model]
    return _FRONTIER_MULTIPLIER if is_frontier(model) else 1.0


def build_chain(category: str, allow_premium: bool) -> list[str]:
    cat = _CATALOG["categories"].get(category, _CATALOG["categories"]["fast_chat"])
    chain = [cat["primary"], *cat["fallbacks"]]
    if not allow_premium:
        # Students keep every cheap model; only pricey ones (e.g. Claude) gated.
        chain = [m for m in chain if not _is_premium_priced(m)]
    chain = [m for m in chain if _has_key(m) and not _circuit_open(m)]
    return chain or ["groq/llama-3.1-8b-instant"]


async def complete(messages: list[dict], *, category: str = "fast_chat",
                   allow_premium: bool = False, temperature: float = 0.7,
                   max_tokens: int | None = None, model: str | None = None,
                   response_format: dict | None = None) -> dict[str, Any]:
    """Non-streaming completion with failover. Returns text + usage + model.

    `response_format={"type": "json_object"}` forces structured JSON output on
    providers that support it (others silently drop it via litellm.drop_params).
    """
    chain = _explicit_chain(model) if model else build_chain(category, allow_premium)
    last_err: Exception | None = None
    for model in chain:
        t0 = time.time()
        try:
            lm, extra = _litellm_target(model)
            kwargs = {"model": lm, "messages": messages, "temperature": temperature, **extra}
            if max_tokens:
                kwargs["max_tokens"] = max_tokens
            if response_format:
                kwargs["response_format"] = response_format
            resp = await litellm.acompletion(**kwargs)
            _record_ok(model, time.time() - t0)
            usage = resp.usage
            p_tok, c_tok = usage.prompt_tokens, usage.completion_tokens
            return {
                "text": resp.choices[0].message.content or "",
                "model": model,
                "prompt_tokens": p_tok,
                "completion_tokens": c_tok,
                "cost_usd": _cost(model, p_tok, c_tok),
            }
        except Exception as e:  # noqa: BLE001
            print(f"[router] model '{model}' failed: {type(e).__name__}: {e}")
            _record_fail(model)
            last_err = e
            continue
    raise RuntimeError(f"All providers exhausted for '{category}'. Last error: {last_err}")


async def stream(messages: list[dict], *, category: str = "fast_chat",
                 allow_premium: bool = False, temperature: float = 0.7,
                 max_tokens: int | None = None, model: str | None = None) -> AsyncIterator[dict]:
    """Stream tokens; yields {'delta': str} then a final {'done': {...usage}}."""
    chain = _explicit_chain(model) if model else build_chain(category, allow_premium)
    last_err: Exception | None = None
    for model in chain:
        t0 = time.time()
        try:
            lm, extra = _litellm_target(model)
            kwargs = {"model": lm, "messages": messages,
                      "temperature": temperature, "stream": True, **extra}
            if max_tokens:
                kwargs["max_tokens"] = max_tokens
            resp = await litellm.acompletion(**kwargs)
            full = ""
            async for part in resp:
                delta = part.choices[0].delta
                # Reasoning models (Kimi/DeepSeek "thinking") stream chain-of-thought
                # in a separate field — surface it so the answer never looks stalled.
                rtok = getattr(delta, "reasoning_content", None) or ""
                if rtok:
                    yield {"reasoning": rtok}
                tok = delta.content or ""
                if tok:
                    full += tok
                    yield {"delta": tok}
            _record_ok(model, time.time() - t0)
            p_tok = sum(
                len(m["content"]) if isinstance(m["content"], str)
                else sum(len(part.get("text", "")) for part in m["content"]
                         if isinstance(part, dict))
                for m in messages
            ) // 4
            c_tok = max(1, len(full) // 4)
            yield {"done": {
                "model": model, "text": full,
                "prompt_tokens": p_tok, "completion_tokens": c_tok,
                "cost_usd": _cost(model, p_tok, c_tok),
            }}
            return
        except Exception as e:  # noqa: BLE001
            print(f"[router] stream model '{model}' failed: {type(e).__name__}: {e}")
            _record_fail(model)
            last_err = e
            continue
    raise RuntimeError(f"All providers exhausted (stream). Last error: {last_err}")


def health() -> dict[str, Any]:
    return {
        "open_circuits": redis_client.list_open_circuits(),
        "p50_latency": {m: round(sorted(d)[len(d) // 2], 3)
                        for m, d in _latency.items() if d},
    }
