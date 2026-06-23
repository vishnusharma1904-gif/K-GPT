"""Web search grounding (P33) — optional, cited.

Uses the DuckDuckGo HTML endpoint (no API key) by default; if a TAVILY_API_KEY
is configured it uses Tavily for better results. Returns a small list of
{title, url, snippet} that the chat layer folds into the prompt as grounded
context and surfaces back to the client as inline citations (P32).

Network-light and fail-soft: any error returns [] so a search never breaks a
chat — the model just answers without grounding.
"""
from __future__ import annotations

import os
import re

import httpx

_UA = {"User-Agent": "Mozilla/5.0 (compatible; K-GPT/1.0; +campus-ai)"}
_TAG = re.compile(r"<[^>]+>")


def _strip(html: str) -> str:
    return _TAG.sub("", html or "").strip()


async def search(query: str, k: int = 4) -> list[dict]:
    """Return up to k web results. Never raises."""
    q = (query or "").strip()
    if not q:
        return []
    try:
        if os.getenv("TAVILY_API_KEY"):
            return await _tavily(q, k)
        return await _duckduckgo(q, k)
    except Exception:  # noqa: BLE001
        return []


async def _tavily(q: str, k: int) -> list[dict]:
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post("https://api.tavily.com/search", json={
            "api_key": os.getenv("TAVILY_API_KEY"),
            "query": q, "max_results": k, "search_depth": "basic",
        })
        r.raise_for_status()
        data = r.json()
    return [{"title": x.get("title", ""), "url": x.get("url", ""),
             "snippet": (x.get("content") or "")[:300]}
            for x in data.get("results", [])[:k]]


async def _duckduckgo(q: str, k: int) -> list[dict]:
    async with httpx.AsyncClient(timeout=10, headers=_UA, follow_redirects=True) as c:
        r = await c.get("https://html.duckduckgo.com/html/", params={"q": q})
        r.raise_for_status()
        html = r.text
    results: list[dict] = []
    for m in re.finditer(
        r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S):
        url, title = m.group(1), _strip(m.group(2))
        if url and title:
            results.append({"title": title, "url": url, "snippet": ""})
        if len(results) >= k:
            break
    # attach snippets where present
    snips = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, re.S)
    for i, s in enumerate(snips[:len(results)]):
        results[i]["snippet"] = _strip(s)[:300]
    return results


def format_context(results: list[dict]) -> str:
    """Render results as a numbered context block for the system prompt."""
    if not results:
        return ""
    lines = ["Web search results (cite as [n] when you use them):"]
    for i, r in enumerate(results, 1):
        lines.append(f"[{i}] {r['title']} — {r['url']}\n{r.get('snippet','')}")
    return "\n".join(lines)
