"""Vision-model OCR for handwriting and scanned pages (backlog §6.4).

Tesseract reads printed text well but is effectively useless on handwriting
(~95% error rate). For 90%+ handwriting accuracy we send the page image to a
cheap multimodal model. The default is Gemini 2.5 Flash-Lite (~$0.001/page) via
the existing GEMINI_API_KEY, but ``ocr_vision_model`` can point at any
litellm-supported vision model (Mistral OCR, a Fireworks Qwen-VL id, etc.) with
no code change.

Everything here is best-effort and returns "" on any failure, so the caller
(extract.py) cleanly falls back to Tesseract / the digital text layer.
"""
from __future__ import annotations

import base64

from app.core.config import get_settings

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
}

_PROMPT = (
    "You are an OCR engine. Transcribe ALL text in this image exactly as written, "
    "including handwriting, cursive, and text inside tables or forms. Preserve line "
    "breaks and reading order. Do NOT translate, summarise, correct spelling, or add "
    "any commentary — output only the raw transcribed text. If the image contains no "
    "legible text, output nothing."
)


def available() -> bool:
    """Whether vision OCR is enabled and its model's provider key is present."""
    import os
    s = get_settings()
    if not s.ocr_vision_enabled or not s.ocr_vision_model:
        return False
    provider = s.ocr_vision_model.split("/", 1)[0]
    env = _PROVIDER_ENV.get(provider)
    # Unknown provider prefix -> assume the operator knows what they're doing.
    return bool(os.getenv(env)) if env else True


def ocr_image(data: bytes, mime: str = "image/png") -> str:
    """Transcribe an image (incl. handwriting) with the configured vision model.
    Returns "" if vision OCR is unavailable or the call fails."""
    if not available() or not data:
        return ""
    s = get_settings()
    try:
        import litellm
        b64 = base64.b64encode(data).decode()
        resp = litellm.completion(
            model=s.ocr_vision_model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": _PROMPT},
                    {"type": "image_url",
                     "image_url": {"url": f"data:{mime};base64,{b64}"}},
                ],
            }],
            temperature=0,
            timeout=60,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:  # noqa: BLE001
        print(f"[warn] vision OCR failed ({s.ocr_vision_model}): {e}")
        return ""
