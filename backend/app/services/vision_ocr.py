"""Vision-model OCR for handwriting and scanned pages.

This path is intentionally stubborn: it tries the pinned OCR model first, then
every configured vision-capable model in the registry, and retries with a
second, simpler OCR prompt before giving up.
"""
from __future__ import annotations

import base64
import json
import os
import threading
import time
from pathlib import Path

from app.core.config import get_settings

_CATALOG = json.loads((Path(__file__).parent / "models.json").read_text())
_REGISTRY = _CATALOG.get("registry", {})

# Provider prefix -> the env var litellm needs for that provider. Used only to
# skip the network call when the relevant key isn't configured.
_PROVIDER_ENV = {
    "gemini": "GEMINI_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "fireworks_ai": "FIREWORKS_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "groq": "GROQ_API_KEY",
    "zenmux": "ZENMUX_API_KEY",
}
_ZENMUX_BASE = "https://zenmux.ai/api/v1"

_PROMPT = (
    "You are an OCR engine. Transcribe ALL text in this image exactly as written, "
    "including handwriting, cursive, printed text, tables, forms, and mixed layouts. "
    "Preserve line breaks and reading order. The image may contain faint ink, blur, "
    "low contrast, ruled paper, shadows, or scanned handwritten notes. Do not "
    "translate, summarize, correct spelling, infer missing words, or add commentary. "
    "Return only the raw transcribed text. If nothing is legible, return an empty response."
)
_PROMPT_FALLBACK = (
    "OCR this image and return only the exact text. Keep line breaks. Read handwriting "
    "if present. If no text is legible, return an empty response."
)

# Classification prompt for the local-OCR handwriting gate (see _looks_handwritten).
# Deliberately terse — this is a one-word yes/no check, not a transcription, so it
# stays cheap and fast on the same pinned cloud model already used for OCR.
_HANDWRITING_CHECK_PROMPT = (
    "Look at this image. Is the main text in it HANDWRITTEN (pen/pencil, cursive or "
    "print-style handwriting) or PRINTED/TYPED (typeset, digital, or machine-printed)? "
    "Reply with exactly one word: HANDWRITTEN or PRINTED."
)


def available() -> bool:
    """Whether vision OCR is enabled and at least one candidate model is usable."""
    s = get_settings()
    if not s.ocr_vision_enabled:
        return False
    return bool(_candidate_models())


def _has_provider_key(model: str) -> bool:
    provider = model.split("/", 1)[0]
    env = _PROVIDER_ENV.get(provider)
    return bool(os.getenv(env)) if env else True


def _litellm_target(model: str) -> tuple[str, dict]:
    if model.startswith("zenmux/"):
        slug = model[len("zenmux/"):]
        return f"openai/{slug}", {
            "api_base": _ZENMUX_BASE,
            "api_key": os.getenv("ZENMUX_API_KEY", ""),
        }
    return model, {}


def _candidate_models() -> list[str]:
    """Pinned OCR model first, then every available vision-capable model."""
    from app.services import smart_router

    s = get_settings()
    candidates: list[str] = []
    pinned = (s.ocr_vision_model or "").strip()
    if pinned and _has_provider_key(pinned):
        candidates.append(pinned)

    chain = smart_router.build_chain("vision", "vision", {"vision": True}).chain
    for model in chain:
        if model not in candidates:
            candidates.append(model)

    for model, meta in _REGISTRY.items():
        if not meta.get("capabilities", {}).get("vision", False):
            continue
        if not _has_provider_key(model):
            continue
        if model not in candidates:
            candidates.append(model)
    return candidates


def _message_variants(b64: str, mime: str) -> list[list[dict]]:
    """Just the one, well-tested prompt. This used to also try a second, simpler
    fallback prompt per model — doubling worst-case latency for every model in
    the chain for a variant that rarely recovered anything the first one
    didn't. With paid-tier keys (real throughput, not free-tier scarcity), the
    time is better spent trying the NEXT model than a second prompt on the same
    one."""
    image_part = {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
    return [
        [{
            "role": "user",
            "content": [
                {"type": "text", "text": _PROMPT},
                image_part,
            ],
        }],
    ]


# Hard wall-clock budget for a SINGLE page/image, across every candidate model,
# prompt variant, and retry. Without this, a degraded/rate-limited primary model
# could burn (models × variants × retries × 90s timeout) minutes on one page —
# on a multi-page document processed with limited concurrency, that turns into
# the whole batch appearing to hang for 9-10+ minutes while only a handful of
# pages (the ones that got lucky/first) ever succeed.
_MAX_SECONDS_PER_PAGE = 75
_PER_CALL_TIMEOUT = 30
_RETRIES = 2
_BACKOFF_BASE = 2

# --- Local/self-hosted OCR — handwriting-only gate ---------------------------
# A locally-hosted model (e.g. Qwen2.5-VL on a rented GPU, reached via an SSH
# tunnel to localhost) is tried ONLY for content classified as handwritten.
# Printed scans and normal documents never reach this path — they fall straight
# through to the existing paid vision chain below, unchanged.
_HANDWRITING_CHECK_TIMEOUT = 15
# 60s wasn't enough headroom on the actual rented box: observed 2026-07-02, a
# successful local-OCR call took 72.5s end-to-end (measured here) / 86s
# end-to-end (measured on the GPU box's own GIN log), while the GPU's OWN
# timing log showed only 5.75s of actual model compute (prompt eval + eval).
# The remaining ~65-80s is almost certainly SSH-tunnel transfer time for the
# base64-encoded page image, not GPU work — this vast.ai instance/region was
# already flagged in the ops notes for wildly inconsistent bandwidth (18 MB/s
# swinging to 697 KB/s on the same box). Raised so a page that's actually
# working, just slow over this tunnel, doesn't get killed right as it's about
# to finish. If you rent a box with better/more consistent bandwidth to this
# location later, both numbers below can come back down.
_LOCAL_OCR_TIMEOUT = 120

# Ollama serializes ALL requests to a multimodal/vision-capable model to a
# SINGLE slot, regardless of OLLAMA_NUM_PARALLEL — confirmed live on the rented
# GPU (2026-07-02): even after setting OLLAMA_NUM_PARALLEL=4 in the systemd
# override and a clean restart, the launched llama-server process still logs
# `-np 1` / `n_slots = 1` for qwen-ocr-fixed. This is a known Ollama limitation
# for multimodal models, not a misconfiguration. extract.py's 12 concurrent OCR
# workers (_OCR_MAX_CONCURRENT) will all try to hit this single slot at once if
# left unguarded — they pile up inside OLLAMA's internal queue, not ours, so
# each one still counts its wait time against _LOCAL_OCR_TIMEOUT below and
# times out before ever getting a turn (observed: one request queued 4m19s and
# still 500'd). This semaphore moves the queueing into Python instead, so pages
# wait their turn HERE — fast, cheap, and NOT counted against the per-call
# HTTP timeout — and only the actual generation time counts against it.
#
# With real per-page time now looking like ~75-90s (mostly tunnel transfer,
# per the note above) rather than the few seconds originally assumed, a page
# queued behind several others needs real room to wait its turn — 90s was
# sized for a fast-GPU assumption that didn't hold up. Raised so up to ~3-4
# queued pages ahead of you don't cause a premature give-up.
_LOCAL_OCR_SLOTS = 1
_LOCAL_OCR_QUEUE_TIMEOUT = 300  # max wait for a turn before giving up and falling back to cloud
_local_ocr_semaphore = threading.Semaphore(_LOCAL_OCR_SLOTS)


def _looks_handwritten(b64: str, mime: str) -> bool:
    """Cheap classification gate: is this image mainly handwritten text?

    Uses the same pinned cloud model already relied on elsewhere in this file —
    no new provider/key required. Fails CLOSED (returns False → normal path) on
    any error, timeout, or ambiguous answer, so a classifier hiccup can never
    accidentally skip the local model INTO the path for printed content; the
    worst case is a handwritten page missing the speed boost, never a printed
    page being mis-routed.
    """
    s = get_settings()
    pinned = (s.ocr_vision_model or "").strip()
    if not pinned or not _has_provider_key(pinned):
        return False
    try:
        import litellm
        target, extra = _litellm_target(pinned)
        resp = litellm.completion(
            model=target,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": _HANDWRITING_CHECK_PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                ],
            }],
            temperature=0,
            max_tokens=5,
            timeout=_HANDWRITING_CHECK_TIMEOUT,
            **extra,
        )
        answer = (resp.choices[0].message.content or "").strip().upper()
        return answer.startswith("HANDWRIT")
    except Exception as e:  # noqa: BLE001
        print(f"[warn] handwriting check failed, treating as printed: {e}")
        return False


_LOCAL_OCR_MAX_PIXELS = 1_000_000


def _downscale_for_local_model(b64: str) -> tuple[str, str]:
    """Downscale an image client-side before sending it to the local Qwen2.5-VL
    model. Returns (b64, mime) — mime is always "image/png" if a resize
    happened, unchanged otherwise.

    Ollama forcibly resizes ANY image fed to qwen2.5vl down to under ~1M pixels
    before the model ever sees it — confirmed via ollama/ollama#11217 on
    GitHub, not a guess. K-GPT renders PDF pages at 300 DPI
    (`extract._ocr_pdf_pages`), and a standard Letter page at 300 DPI is
    ~2550x3300px = ~8.4M pixels, over 8x that cap. That means every page was
    being crushed down by Ollama's own (unknown-quality, uncontrolled) internal
    resize before the model could read it — the most likely cause of the
    confident-but-wrong hallucinated transcriptions seen in testing
    (2026-07-02): a sufficiently mangled image gives an instruction-following
    model no real signal, and it fills the gap with a plausible-sounding
    fabrication instead of admitting it can't read the page.

    Doing the downscale HERE instead of leaving it to Ollama: (1) uses a
    proper high-quality filter (LANCZOS) instead of whatever Ollama does
    internally, (2) meaningfully shrinks what actually crosses the SSH tunnel,
    since the extra detail above ~1M pixels was being thrown away anyway —
    this should also help the tunnel-transfer-time problem from earlier in the
    same session. Falls back to the original (b64, mime) on any error — a
    resize bug must never block OCR entirely.
    """
    try:
        import io
        from PIL import Image
        raw = base64.b64decode(b64)
        img = Image.open(io.BytesIO(raw))
        w, h = img.size
        pixels = w * h
        if pixels <= _LOCAL_OCR_MAX_PIXELS:
            return b64, "image/png"
        scale = (_LOCAL_OCR_MAX_PIXELS / pixels) ** 0.5
        new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))
        img = img.convert("RGB").resize((new_w, new_h), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        print(f"[info] local OCR: downscaled {w}x{h} ({pixels:,}px) -> "
              f"{new_w}x{new_h} ({new_w * new_h:,}px) before sending to GPU")
        return base64.b64encode(buf.getvalue()).decode(), "image/png"
    except Exception as e:  # noqa: BLE001
        print(f"[warn] local OCR image downscale failed, sending original: {e}")
        return b64, "image/png"


def _local_ocr(b64: str, mime: str) -> str:
    """Try the self-hosted local model (rented GPU via SSH tunnel). Never raises —
    returns '' on any failure so the caller falls back to the normal paid chain.

    Serializes through `_local_ocr_semaphore` (see its comment above) because
    Ollama itself only runs ONE request at a time for this multimodal model no
    matter how many of extract.py's concurrent OCR workers call in — without
    this gate they'd all queue inside Ollama instead of here, and each one's
    wait time would count against `_LOCAL_OCR_TIMEOUT` below, timing out before
    ever getting a turn.

    Records the outcome (hit/miss + latency/error) via redis_client so the
    /api/status page can show whether this path is actually being used, since
    a dead tunnel fails completely silently otherwise — see redis_client.py's
    "Local OCR usage tracking" section for why."""
    s = get_settings()
    if not s.local_ocr_enabled:
        return ""
    from app.db import redis_client

    # See _downscale_for_local_model's docstring: Ollama crushes any image over
    # ~1M pixels down internally anyway (confirmed via ollama/ollama#11217), so
    # a full 300-DPI page render was arriving illegible — this is the fix for
    # the hallucinated-transcription bug found in testing on 2026-07-02. Still
    # applied for vLLM too: it doesn't have Ollama's silent forced-resize bug,
    # but Qwen2.5-VL's own recommended operating range is similar (~1M pixels)
    # and there's no reason to pay the tunnel-transfer cost for detail the
    # model wouldn't meaningfully use anyway.
    local_b64, local_mime = _downscale_for_local_model(b64)

    # Backend-agnostic: "ollama_chat/..." uses Ollama's single-slot serving
    # (needs the semaphore below); "openai/..." targets a vLLM OpenAI-
    # compatible server, which does real continuous batching server-side —
    # forcing client-side serialization on top of that would just throw away
    # the concurrency vLLM is specifically good at, so it's skipped entirely
    # for that backend.
    is_ollama = s.local_ocr_model.startswith("ollama_chat/")

    if is_ollama and not _local_ocr_semaphore.acquire(timeout=_LOCAL_OCR_QUEUE_TIMEOUT):
        print(f"[warn] local OCR (rented GPU) queue wait exceeded {_LOCAL_OCR_QUEUE_TIMEOUT}s "
              "— falling back to cloud chain")
        redis_client.ocr_local_record(False, error=f"queue wait exceeded {_LOCAL_OCR_QUEUE_TIMEOUT}s")
        return ""

    try:
        start = time.monotonic()
        try:
            import litellm
            kwargs: dict = dict(
                model=s.local_ocr_model,
                api_base=s.local_ocr_api_base,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _PROMPT},
                        {"type": "image_url", "image_url": {"url": f"data:{local_mime};base64,{local_b64}"}},
                    ],
                }],
                temperature=0,
                max_tokens=4096,
                timeout=_LOCAL_OCR_TIMEOUT,
            )
            if is_ollama:
                # Previously set by the now-abandoned "qwen-ocr-fixed" Modelfile
                # (PARAMETER num_ctx 8192). Targeting the base qwen2.5vl:7b
                # model directly, so this has to be passed per-request instead —
                # Ollama's default 4096 context overflows on a full-page image +
                # prompt, silently truncating output. litellm forwards num_ctx
                # straight through to Ollama for the ollama_chat provider.
                kwargs["num_ctx"] = 8192
            else:
                # vLLM's context length is fixed server-side at launch
                # (--max-model-len), not per-request — nothing to pass here.
                # It does need an api_key for the OpenAI-compatible client
                # path even when the server doesn't actually check it.
                kwargs["api_key"] = s.local_ocr_api_key
            resp = litellm.completion(**kwargs)
            text = (resp.choices[0].message.content or "").strip()
            elapsed = time.monotonic() - start
            if text:
                # Was silent on success before — meant a clean run produced ZERO
                # log lines, so there was no way to watch per-page GPU timing
                # live while a document was processing. This line is what
                # "docker compose logs -f backend" now shows for each
                # handwritten page the GPU handles.
                print(f"[info] local OCR (rented GPU) page done in {elapsed:.1f}s ({len(text)} chars)")
                redis_client.ocr_local_record(True, latency_s=elapsed)
            else:
                redis_client.ocr_local_record(False, error="empty response")
            return text
        except Exception as e:  # noqa: BLE001
            print(f"[warn] local OCR (rented GPU) unavailable, falling back to cloud chain: {e}")
            redis_client.ocr_local_record(False, error=str(e))
            return ""
    finally:
        if is_ollama:
            _local_ocr_semaphore.release()


def ocr_image(data: bytes, mime: str = "image/png", *, models: list[str] | None = None,
             rotate: int = 0, allow_local: bool = False) -> str:
    """Transcribe an image (including handwriting) using all available vision models.

    Bounded to `_MAX_SECONDS_PER_PAGE` total so one bad/rate-limited page can't
    stall an entire multi-page batch — callers processing many pages concurrently
    rely on this to keep overall wall-clock time bounded.

    `models`/`rotate` let a multi-page caller (e.g. `extract._ocr_pdf_pages`)
    spread concurrent pages across DIFFERENT models instead of every page racing
    the same pinned model first. Without this, N concurrent pages all hit model
    #1 simultaneously, all trip its rate limit together, then all fall back to
    model #2 together, etc. — worst-case lockstep contention instead of real
    parallelism. `rotate` shifts the candidate list's starting point per page
    (e.g. page 3 of 4 concurrent pages starts at candidates[3 % len]).

    `allow_local`: opt-in gate for the rented-GPU local model. Only
    `extract._ocr_pdf_pages` (multi-page documents) passes `allow_local=True`.
    Standalone image uploads and embedded DOCX/PPTX pictures deliberately leave
    this False, so a photo of handwriting uploaded on its own always uses the
    normal cloud chain — the local GPU is reserved for handwritten *documents*
    only, never handwritten *images*.
    """
    if not data:
        return ""
    b64 = base64.b64encode(data).decode()

    # Handwriting-only local-GPU gate. Printed scans, standalone image uploads,
    # and everything else fall straight through to the untouched cloud chain
    # below — only handwritten PAGES OF A DOCUMENT (allow_local=True) ever
    # reach the rented-GPU model, and even then only if it actually returns
    # text; any failure (tunnel down, model not loaded, timeout) silently
    # falls back to the normal path.
    s = get_settings()
    if allow_local and s.local_ocr_enabled and _looks_handwritten(b64, mime):
        local_text = _local_ocr(b64, mime)
        if local_text:
            return local_text
        print("[info] local OCR (rented GPU) returned nothing usable — falling back to cloud chain")

    models = list(models) if models is not None else _candidate_models()
    if not models:
        return ""
    if rotate:
        r = rotate % len(models)
        models = models[r:] + models[:r]
    try:
        import litellm
    except Exception as e:  # noqa: BLE001
        print(f"[warn] vision OCR unavailable: {e}")
        return ""

    start = time.monotonic()
    for model in models:
        if time.monotonic() - start > _MAX_SECONDS_PER_PAGE:
            print(f"[warn] OCR page budget ({_MAX_SECONDS_PER_PAGE}s) exhausted before trying {model}")
            break
        target, extra = _litellm_target(model)
        for messages in _message_variants(b64, mime):
            if time.monotonic() - start > _MAX_SECONDS_PER_PAGE:
                break
            for attempt in range(_RETRIES):
                try:
                    resp = litellm.completion(
                        model=target,
                        messages=messages,
                        temperature=0,
                        timeout=_PER_CALL_TIMEOUT,
                        # No cap here defaults to a small provider max (often
                        # 512-2048 tokens on free/lite tiers), which silently
                        # truncates a dense handwritten page mid-transcription —
                        # the response still "succeeds", it's just incomplete.
                        # This is generous enough for a full page of dense text.
                        max_tokens=4096,
                        **extra,
                    )
                    text = (resp.choices[0].message.content or "").strip()
                    if text:
                        return text
                    break
                except Exception as e:
                    err_str = str(e).lower()
                    is_rate_limit = any(x in err_str for x in ["429", "rate", "quota", "resource_exhausted"])
                    remaining = _MAX_SECONDS_PER_PAGE - (time.monotonic() - start)
                    if is_rate_limit and attempt < _RETRIES - 1 and remaining > _BACKOFF_BASE:
                        sleep_time = min(_BACKOFF_BASE * (2 ** attempt), remaining)
                        print(f"[warn] OCR rate limited ({model}). Retrying in {sleep_time:.0f}s... Error: {e}")
                        time.sleep(sleep_time)
                        continue
                    else:
                        print(f"[warn] vision OCR failed ({model}): {e}")
                        break
    return ""


# --- Batched multi-page OCR --------------------------------------------------
# ChatGPT/Gemini feel far faster on the same multi-page scan mainly because
# they send the WHOLE document (or large chunks of it) to their own model in
# one request; K-GPT was doing one network round-trip per page. Round-trip +
# provider queueing overhead, not token-processing time, dominates a small-image
# OCR call, so batching several pages into one completion call is the single
# biggest lever available — turning e.g. 17 round-trips into ~4-5.
_BATCH_DELIM = "@@KGPT_PAGE_BREAK@@"
_BATCH_MAX_SECONDS = 50   # keep a multi-page document's total OCR well under 60s
_BATCH_CALL_TIMEOUT = 35  # a batched call carries more image tokens than one page


def _batch_prompt(n: int) -> str:
    return (
        f"You are an OCR engine. You will be shown {n} separate page images from a "
        "handwritten/scanned document, in the order given. Transcribe ALL text in "
        "EACH image exactly as written, including handwriting, cursive, printed "
        "text, tables, forms, and mixed layouts. Preserve line breaks and reading "
        "order within each page. Do not translate, summarize, correct spelling, "
        "infer missing words, or add commentary.\n\n"
        f"Output EXACTLY {n} sections, one per image in the order shown, each "
        f"separated by a line containing ONLY: {_BATCH_DELIM}\n"
        "Do not add any other text, headers, page numbers, or numbering of your "
        f"own — only the transcriptions, separated by {_BATCH_DELIM}. If a page has "
        "no legible text, leave its section empty (but still include the "
        "separator)."
    )


def ocr_images_batch(images: list[bytes], mime: str = "image/png", *,
                     models: list[str] | None = None, rotate: int = 0) -> list[str] | None:
    """Transcribe multiple page images in ONE model call. Returns a list of
    per-image transcriptions in order, or None if the model's response couldn't
    be reliably split back into exactly len(images) sections — callers MUST
    fall back to per-page `ocr_image` in that case rather than risk silently
    misattributing text to the wrong page (e.g. a page shifted off-by-one)."""
    if not images:
        return []
    n = len(images)
    models = list(models) if models is not None else _candidate_models()
    if not models:
        return None
    if rotate:
        r = rotate % len(models)
        models = models[r:] + models[:r]
    try:
        import litellm
    except Exception:
        return None

    content: list[dict] = [{"type": "text", "text": _batch_prompt(n)}]
    for img in images:
        b64 = base64.b64encode(img).decode()
        content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
    messages = [{"role": "user", "content": content}]

    start = time.monotonic()
    for model in models:
        if time.monotonic() - start > _BATCH_MAX_SECONDS:
            break
        target, extra = _litellm_target(model)
        for attempt in range(_RETRIES):
            try:
                resp = litellm.completion(
                    model=target,
                    messages=messages,
                    temperature=0,
                    timeout=_BATCH_CALL_TIMEOUT,
                    **extra,
                )
                text = (resp.choices[0].message.content or "").strip()
                parts = [p.strip() for p in text.split(_BATCH_DELIM)]
                if len(parts) == n:
                    return parts
                print(f"[warn] batch OCR ({model}) returned {len(parts)} sections, expected {n} — "
                      f"falling back to per-page OCR for this batch")
                break
            except Exception as e:
                err_str = str(e).lower()
                is_rate_limit = any(x in err_str for x in ["429", "rate", "quota", "resource_exhausted"])
                remaining = _BATCH_MAX_SECONDS - (time.monotonic() - start)
                if is_rate_limit and attempt < _RETRIES - 1 and remaining > _BACKOFF_BASE:
                    sleep_time = min(_BACKOFF_BASE * (2 ** attempt), remaining)
                    time.sleep(sleep_time)
                    continue
                print(f"[warn] batch OCR failed ({model}): {e}")
                break
    return None
