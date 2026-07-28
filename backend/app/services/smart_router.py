"""K-GPT SmartRouter (v8) — Capabilities-based routing with failover.
"""
from __future__ import annotations

import json
import os
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator

import litellm

litellm.suppress_debug_info = True
litellm.drop_params = True

from app.db import redis_client

_CATALOG = json.loads((Path(__file__).parent / "models.json").read_text())
_MODES = _CATALOG.get("modes", {})
_REGISTRY = _CATALOG.get("registry", {})
_PROVIDER_ENV = _CATALOG.get("provider_env", {})

_fail_counts: dict[str, int] = defaultdict(int)
_latency: dict[str, deque] = defaultdict(lambda: deque(maxlen=20))
_in_flight: dict[str, int] = defaultdict(int)

_TRIP_AFTER = 3
_OPEN_SECONDS_MODEL = 300   # 5 mins for 429
_OPEN_SECONDS_PROVIDER = 300 # 5 mins for 5xx

_MAX_CONCURRENT_PER_PROVIDER = 20
_ZENMUX_BASE = "https://zenmux.ai/api/v1"

@dataclass
class RoutingDecision:
    mode: str
    intent: str
    subtype: str
    chain: list[str]
    confidence: float
    reason: str

    def to_dict(self):
        return {
            "mode": self.mode,
            "intent": self.intent,
            "subtype": self.subtype,
            "chain": self.chain,
            "confidence": self.confidence,
            "reason": self.reason
        }

def _is_zenmux(model: str) -> bool:
    return model.startswith("zenmux/")

def _litellm_target(model: str) -> tuple[str, dict]:
    if _is_zenmux(model):
        slug = model[len("zenmux/"):]
        return f"openai/{slug}", {"api_base": _ZENMUX_BASE, "api_key": os.getenv("ZENMUX_API_KEY", "")}
    return model, {}

def _has_key(provider: str) -> bool:
    env = _PROVIDER_ENV.get(provider)
    return bool(os.getenv(env)) if env else True


def _eligible_models(capabilities_required: dict[str, bool]) -> list[str]:
    """All configured models that satisfy the requested capabilities."""
    out: list[str] = []
    for mid, reg in _REGISTRY.items():
        provider = reg.get("provider", mid.split("/")[0])
        caps = reg.get("capabilities", {})
        if any(v and not caps.get(k, False) for k, v in capabilities_required.items()):
            continue
        if not _has_key(provider):
            continue
        if _circuit_open(f"provider:{provider}") or _circuit_open(mid):
            continue
        if _in_flight.get(provider, 0) >= _MAX_CONCURRENT_PER_PROVIDER:
            continue
        out.append(mid)
    return out

def _circuit_open(key: str) -> bool:
    return redis_client.circuit_is_open(key)

def _record_fail(model: str, status_code: int) -> None:
    provider = _REGISTRY.get(model, {}).get("provider", model.split("/")[0])
    if status_code == 429:
        _fail_counts[model] += 1
        if _fail_counts[model] >= _TRIP_AFTER:
            redis_client.circuit_trip(model, _OPEN_SECONDS_MODEL)
    elif status_code in (500, 502, 503, 504, 401, 403):
        prov_key = f"provider:{provider}"
        _fail_counts[prov_key] += 1
        if _fail_counts[prov_key] >= _TRIP_AFTER or status_code in (401, 403):
            redis_client.circuit_trip(prov_key, _OPEN_SECONDS_PROVIDER)

def _record_ok(model: str, dt: float) -> None:
    provider = _REGISTRY.get(model, {}).get("provider", model.split("/")[0])
    _fail_counts[model] = 0
    _fail_counts[f"provider:{provider}"] = 0
    _latency[model].append(dt)

def _cost(model: str, p_tok: int, c_tok: int) -> float:
    px = _REGISTRY.get(model, {}).get("pricing", {"in": 0.5, "out": 0.5})
    return round(p_tok / 1e6 * px["in"] + c_tok / 1e6 * px["out"], 6)

def _params_billions(model: str) -> float:
    tail = model.lower()
    best = 0.0
    for a, b in re.findall(r"(\d+)x(\d+)b", tail):
        best = max(best, int(a) * int(b))
    for n in re.findall(r"(?<![x\d])(\d+)b", tail):
        best = max(best, float(n))
    return best

def is_frontier(model: str) -> bool:
    px = _REGISTRY.get(model, {}).get("pricing", {"in": 0.5, "out": 0.5})
    if (px.get("in", 0) + px.get("out", 0)) > 1.0:
        return True
    if _params_billions(model) > 40:
        return True
    return any(k in model.lower() for k in ("ultra", "opus", "405b", "-max"))

def cost_multiplier(model: str) -> float:
    if model == "groq/llama-3.3-70b-versatile":
        return 1.5
    return 3.5 if is_frontier(model) else 1.0

def selectable_models() -> list[dict]:
    out = []
    for mid, mdata in _REGISTRY.items():
        prov = mdata.get("provider", mid.split("/")[0])
        px = mdata.get("pricing", {"out": 0.5})
        out.append({
            "id": mid,
            "label": mid.split("/")[-1].replace("-", " ").title(),
            "provider": prov,
            "provider_label": prov.title(),
            "price_out": px.get("out", 0.5),
            "available": _has_key(prov),
            "frontier": is_frontier(mid),
            "multiplier": cost_multiplier(mid),
        })
    return out

def build_chain(mode: str, intent: str, capabilities_required: dict[str, bool]) -> RoutingDecision:
    raw_chain = None
    if intent in _MODES and intent != "general":
        raw_chain = _MODES[intent]
    else:
        raw_chain = _MODES.get(mode, _MODES.get("general", []))

    valid_chain: list[str] = []
    for m in list(raw_chain) + _eligible_models(capabilities_required):
        if m not in valid_chain:
            valid_chain.append(m)

    return RoutingDecision(
        mode=mode,
        intent=intent,
        subtype="",
        chain=valid_chain,
        confidence=1.0,
        reason="Resolved via models.json mapping"
    )

async def complete(messages: list[dict], *, mode: str = "general", intent: str = "general",
                   capabilities_required: dict | None = None, temperature: float = 0.7,
                   max_tokens: int | None = None, response_format: dict | None = None,
                   model: str | None = None) -> dict[str, Any]:
    caps = capabilities_required or {}
    if model:
        decision = RoutingDecision(mode="custom", intent="custom", subtype="", chain=[model], confidence=1.0, reason="User explicitly selected model")
    else:
        decision = build_chain(mode, intent, caps)
    chain = decision.chain
    
    if not chain:
        return {"text": "Our AI providers are temporarily unavailable. Please try again in a few moments.", "model": "none", "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0, "decision": decision}
        
    last_err = None
    for model in chain:
        provider = _REGISTRY.get(model, {}).get("provider", model.split("/")[0])
        _in_flight[provider] += 1
        t0 = time.time()
        try:
            lm, extra = _litellm_target(model)
            kwargs = {"model": lm, "messages": messages, "temperature": temperature, **extra}
            if max_tokens: kwargs["max_tokens"] = max_tokens
            if response_format: kwargs["response_format"] = response_format
            
            resp = await litellm.acompletion(**kwargs)
            _record_ok(model, time.time() - t0)
            usage = resp.usage
            return {
                "text": resp.choices[0].message.content or "",
                "model": model,
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "cost_usd": _cost(model, usage.prompt_tokens, usage.completion_tokens),
                "decision": decision
            }
        except litellm.exceptions.APIError as e:
            status = getattr(e, "status_code", 500)
            _record_fail(model, status)
            if status == 400:
                raise RuntimeError(f"Bad Request to {model}: {e}")
            last_err = e
            continue
        except Exception as e:
            _record_fail(model, 500)
            last_err = e
            continue
        finally:
            _in_flight[provider] -= 1

    raise RuntimeError(f"All providers exhausted. Last error: {last_err}")

async def stream(messages: list[dict], *, mode: str = "general", intent: str = "general",
                 capabilities_required: dict | None = None, temperature: float = 0.7,
                 max_tokens: int | None = None, model: str | None = None) -> AsyncIterator[dict]:
    caps = capabilities_required or {}
    if model:
        decision = RoutingDecision(mode="custom", intent="custom", subtype="", chain=[model], confidence=1.0, reason="User explicitly selected model")
    else:
        decision = build_chain(mode, intent, caps)
    chain = decision.chain
    
    if not chain:
        yield {"delta": "Our AI providers are temporarily unavailable. Please try again in a few moments."}
        yield {"done": {"model": "none", "text": "Our AI providers are temporarily unavailable. Please try again in a few moments.", "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0, "decision": decision.to_dict()}}
        return
        
    last_err = None
    for model in chain:
        provider = _REGISTRY.get(model, {}).get("provider", model.split("/")[0])
        _in_flight[provider] += 1
        t0 = time.time()
        try:
            lm, extra = _litellm_target(model)
            kwargs = {"model": lm, "messages": messages, "temperature": temperature, "stream": True, **extra}
            if max_tokens: kwargs["max_tokens"] = max_tokens
            
            resp = await litellm.acompletion(**kwargs)
            full = ""
            async for part in resp:
                delta = part.choices[0].delta
                rtok = getattr(delta, "reasoning_content", None) or ""
                if rtok: yield {"reasoning": rtok}
                tok = delta.content or ""
                if tok:
                    full += tok
                    yield {"delta": tok}
                    
            _record_ok(model, time.time() - t0)
            p_tok = sum(len(m["content"]) if isinstance(m["content"], str) else sum(len(part.get("text", "")) for part in m["content"] if isinstance(part, dict)) for m in messages) // 4
            c_tok = max(1, len(full) // 4)
            yield {"done": {
                "model": model, "text": full,
                "prompt_tokens": p_tok, "completion_tokens": c_tok,
                "cost_usd": _cost(model, p_tok, c_tok),
                "decision": decision.to_dict()
            }}
            return
        except litellm.exceptions.APIError as e:
            status = getattr(e, "status_code", 500)
            _record_fail(model, status)
            if status == 400:
                raise RuntimeError(f"Bad Request to {model}: {e}")
            last_err = e
            continue
        except Exception as e:
            _record_fail(model, 500)
            last_err = e
            continue
        finally:
            _in_flight[provider] -= 1
            
    yield {"delta": "Our AI providers are temporarily unavailable. Please try again in a few moments."}
    yield {"done": {"model": "none", "text": "Our AI providers are temporarily unavailable. Please try again in a few moments.", "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0, "decision": decision.to_dict()}}

def health() -> dict[str, Any]:
    return {
        "open_circuits": redis_client.list_open_circuits(),
        "p50_latency": {m: round(sorted(d)[len(d) // 2], 3) for m, d in _latency.items() if d},
        "in_flight": dict(_in_flight)
    }
