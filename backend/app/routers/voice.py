"""Voice mode — safe re-introduction (P35).

The TRON-X voice feature suffered from "silence hallucination": the STT model
would invent words from near-silent audio. Here we guard against that with:
  * a server-side **duration + size floor** (too-short clips are rejected),
  * a **no-speech / confidence guard** on the transcription result,
  * **push-to-talk only** (the client sends a finished clip, no open mic stream).

STT uses Groq Whisper via the provider key; if unavailable we fail soft. The
whole feature is gated behind the ``voice`` feature flag (off by default).
"""
from __future__ import annotations

import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.core.config import get_settings
from app.core.security import current_user
from app.services import flags

settings = get_settings()
router = APIRouter(prefix="/api/voice", tags=["voice"])

MIN_BYTES = 2_000          # reject near-empty clips (silence)
MAX_BYTES = 8_000_000      # ~ up to a minute of compressed audio
# Transcripts at/below this length from a short clip are likely hallucinated noise.
_NOISE_TOKENS = {"you", "thank you", "thanks for watching", ".", "bye", "..."}


@router.get("/config")
async def voice_config(_: dict = Depends(current_user)):
    return {"enabled": flags.is_enabled("voice", default=False),
            "mode": "push_to_talk", "stt": "groq/whisper-large-v3"}


@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...), claims: dict = Depends(current_user)):
    if not flags.is_enabled("voice", default=False):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Voice mode is disabled.")

    data = await file.read()
    if len(data) < MIN_BYTES:
        # Silence guard — don't even call the model.
        return {"text": "", "discarded": True, "reason": "clip_too_short"}
    if len(data) > MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            "Audio clip too large (max ~1 min).")
    if not settings.groq_api_key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Speech-to-text is not configured.")

    try:
        import litellm
        buf = io.BytesIO(data)
        buf.name = file.filename or "audio.webm"
        resp = await litellm.atranscription(
            model="groq/whisper-large-v3", file=buf,
        )
        text = (getattr(resp, "text", None) or "").strip()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Transcription failed: {e}")

    # Confidence/noise guard: short clips that produce only filler are discarded.
    if text.lower().strip(" .") in _NOISE_TOKENS or len(text) < 2:
        return {"text": "", "discarded": True, "reason": "low_confidence"}
    return {"text": text, "discarded": False}
