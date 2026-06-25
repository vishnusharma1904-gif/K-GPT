"""Figure storage for the document image gallery (backlog §6.1).

Embedded images pulled from uploaded documents are written to a local directory
(``FIGURES_DIR``) and served back read-only via ``/api/figures/...``. This keeps
the feature dependency-free for the demo; swapping the two functions below for an
object-store (S3/Supabase Storage) is the production upgrade path.

Everything here is best-effort: a storage failure must never break an upload, so
callers treat an empty return as "no gallery" rather than an error.
"""
from __future__ import annotations

import os
import re
import uuid

_FIGURES_DIR = os.environ.get("FIGURES_DIR", "static/figures")
_SAFE = re.compile(r"[^A-Za-z0-9._-]")


def _safe(name: str) -> str:
    """Defang a path component so it can never traverse outside the figures dir."""
    return _SAFE.sub("_", name or "")[:80] or "f"


def save_figures(doc_id: str, figures: list[dict]) -> list[dict]:
    """Persist extracted figures and return [{"url", "page"}] gallery entries.

    `figures` is the output of ``extract.extract_figures`` — each item carries
    raw `bytes`, an `ext`, and an optional `page`."""
    if not figures:
        return []
    doc_id = _safe(doc_id) or uuid.uuid4().hex
    out: list[dict] = []
    try:
        target = os.path.join(_FIGURES_DIR, doc_id)
        os.makedirs(target, exist_ok=True)
        for i, fig in enumerate(figures):
            raw = fig.get("bytes")
            if not raw:
                continue
            ext = _safe(fig.get("ext") or "png").lstrip(".") or "png"
            fname = f"{i:03d}.{ext}"
            with open(os.path.join(target, fname), "wb") as fh:
                fh.write(raw)
            out.append({"url": f"/api/figures/{doc_id}/{fname}", "page": fig.get("page")})
    except Exception as e:  # noqa: BLE001
        print(f"[warn] could not store figures for {doc_id}: {e}")
        return []
    return out


def figure_path(doc_id: str, name: str) -> str | None:
    """Resolve a stored figure to an absolute path, or None if it escapes the
    figures root / doesn't exist."""
    root = os.path.abspath(_FIGURES_DIR)
    p = os.path.abspath(os.path.join(root, _safe(doc_id), _safe(name)))
    if not p.startswith(root + os.sep):
        return None
    return p if os.path.isfile(p) else None
