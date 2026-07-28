"""Document text extraction + chunking for RAG ingestion (P29).

Supports PDF, DOCX, PPTX, XLSX, CSV, and plain text. Heavy parsers are imported
lazily so the module loads even if an optional dependency is missing — an
unsupported type raises a clean, user-facing error instead of crashing import.

Extraction → `chunk()` → embed → per-user pgvector memory (kind='document').
The chat RAG path already searches that memory, so upload is the only new wiring.
"""
from __future__ import annotations

import csv
import io
import re

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"}
SUPPORTED = {".pdf", ".docx", ".pptx", ".xlsx", ".xls", ".csv", ".txt", ".md"} | IMAGE_EXTS
MAX_MB = 50
MAX_BYTES = MAX_MB * 1024 * 1024  # upload size guard


class ExtractError(Exception):
    """Raised with a user-safe message when extraction can't proceed."""


def _ext(filename: str) -> str:
    return ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""


def extract_text(filename: str, data: bytes) -> str:
    """Return the plain text of an uploaded file. Raises ExtractError on failure."""
    if len(data) > MAX_BYTES:
        raise ExtractError(f"File is too large (max {MAX_MB} MB).")
    ext = _ext(filename)
    if ext not in SUPPORTED:
        raise ExtractError(
            f"Unsupported file type '{ext or '?'}'. "
            "Upload PDF, DOCX, PPTX, XLSX, CSV, TXT, or MD."
        )
    try:
        if ext == ".pdf":
            return _pdf(data)
        if ext == ".docx":
            return _docx(data)
        if ext == ".pptx":
            return _pptx(data)
        if ext in (".xlsx", ".xls"):
            return _xlsx(data)
        if ext == ".csv":
            return _csv(data)
        if ext in IMAGE_EXTS:
            mime = "image/jpeg" if ext in (".jpg", ".jpeg") else f"image/{ext.lstrip('.')}"
            text = ocr_image(data, mime)
            if not text.strip():
                raise ExtractError(
                    "Couldn't read any text from that image. OCR may be "
                    "unavailable on the server, or the image has no readable text."
                )
            return text
        return data.decode("utf-8", errors="replace")  # .txt / .md
    except ExtractError:
        raise
    except Exception as e:  # noqa: BLE001
        raise ExtractError(f"Couldn't read this file ({type(e).__name__}).") from e


# A page with fewer than this many extracted characters is treated as having no
# real text layer (i.e. scanned/image-only) and is sent to OCR when available.
_OCR_MIN_CHARS_PER_PAGE = 24
_OCR_SUSPECT_CHARS_WITH_IMAGE = 220
_OCR_SUSPECT_WORDS_WITH_IMAGE = 40

# Each page is OCR'd as its OWN single-image call (identical code path to a
# standalone image upload, which is reliable) — NOT batched multiple-pages-per-
# call. Batching was tried and reverted: cramming 4 dense handwritten page
# images into one multimodal call regularly produced truncated/incomplete
# transcriptions per page (small/free-tier vision models silently cut off
# output well before covering all 4 images), which is why a 17-page scan was
# only yielding ~11 short chunks of content instead of a full transcription.
# Real parallelism (many pages in flight at once, each a clean single-image
# call) gets the same wall-clock win without the quality loss.
_OCR_MAX_CONCURRENT = 12


def _page_needs_ocr(page, text: str) -> bool:
    """Heuristic for scanned/handwritten PDF pages.

    Some handwritten PDFs contain a tiny broken text layer from the scanner or a
    few watermark characters, so `page.get_text()` is non-empty but still
    unusable. We OCR such pages too when the page is image-heavy and the text
    looks sparse/garbled.
    """
    stripped = (text or "").strip()
    if len(stripped) < _OCR_MIN_CHARS_PER_PAGE:
        return True

    try:
        has_images = bool(page.get_images(full=True))
        has_drawings = bool(page.get_drawings())
    except Exception:
        has_images = False
        has_drawings = False
    if not (has_images or has_drawings):
        return False

    words = re.findall(r"\w+", stripped)
    if len(stripped) < _OCR_SUSPECT_CHARS_WITH_IMAGE:
        return True
    if len(words) < _OCR_SUSPECT_WORDS_WITH_IMAGE:
        return True
    short_ratio = (sum(1 for w in words if len(w) <= 2) / len(words)) if words else 1.0
    alnum_ratio = (sum(1 for ch in stripped if ch.isalnum()) / len(stripped)) if stripped else 0.0
    return short_ratio > 0.55 or alnum_ratio < 0.55


def _merge_page_text(original: str, ocr: str) -> str:
    """Prefer OCR when it clearly recovered more readable content."""
    base = (original or "").strip()
    ocr = (ocr or "").strip()
    if not ocr:
        return original
    if not base:
        return ocr
    if base.lower() == ocr.lower():
        return original
    if base.lower() in ocr.lower():
        return ocr
    if len(ocr) >= int(len(base) * 1.2):
        return ocr
    return original


def pdf_needs_ocr(data: bytes | None = None, path: str | None = None) -> bool:
    """Fast pre-check: does this PDF have any page that will need vision OCR
    (scanned/handwritten content)? Used by the upload router to decide whether a
    document must be routed to background processing instead of the fast inline
    path — vision OCR can take tens of seconds per page, so it must never run
    inline on the request path (that would block the request, and on a
    single-worker deployment, the whole server).

    Fails safe: any error opening/parsing the file is treated as "needs OCR" so
    we default toward the slower-but-non-blocking background path rather than
    risking a multi-minute inline stall.
    """
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(path) if path else fitz.open(stream=data, filetype="pdf")
        with doc:
            for page in doc:
                if _page_needs_ocr(page, page.get_text()):
                    return True
        return False
    except Exception:
        return True


def _pdf(data: bytes) -> str:
    import fitz  # PyMuPDF
    parts: list[str] = []
    needs_ocr: list[int] = []
    with fitz.open(stream=data, filetype="pdf") as doc:
        for i, page in enumerate(doc):
            txt = page.get_text()
            parts.append(txt)
            if _page_needs_ocr(page, txt):
                needs_ocr.append(i)

        # Scanned / image-only pages have no digital text layer. OCR them so the
        # content is still searchable (backlog §6.4). Best-effort: if Tesseract /
        # its Python binding isn't installed, we keep whatever text we have.
        if needs_ocr:
            ocr = _ocr_pdf_pages(doc, needs_ocr)
            failed = [i for i in needs_ocr if not (ocr.get(i) or "").strip()]
            for i, text in ocr.items():
                if text.strip():
                    parts[i] = _merge_page_text(parts[i], text)
            if failed:
                # Surface partial OCR failure explicitly instead of silently
                # dropping pages — otherwise a 30-page handwritten scan where
                # only a few pages transcribed just looks like a short document,
                # with no signal to the user or the model about what's missing.
                pages_1based = ", ".join(str(i + 1) for i in failed)
                parts.append(
                    f"\n[OCR note: {len(failed)} of {len(needs_ocr)} scanned/handwritten "
                    f"page(s) could not be transcribed and may be missing from this "
                    f"document's searchable content: page(s) {pages_1based}. Consider "
                    f"re-scanning those pages at higher contrast/resolution and "
                    f"re-uploading if this content is important.]"
                )
    return "\n".join(parts)


def _ocr_pdf_pages(doc, page_indexes: list[int]) -> dict[int, str]:
    """OCR the given PDF pages with the app's configured vision models in parallel."""
    try:
        import fitz  # PyMuPDF
    except Exception:
        return {}

    from concurrent.futures import ThreadPoolExecutor
    from app.services import vision_ocr

    out: dict[int, str] = {}
    pages_to_process: list[tuple[int, bytes]] = []

    # 1. Render pages sequentially to avoid PyMuPDF multi-threading context issues
    for i in page_indexes:
        try:
            # 300 DPI improves handwriting OCR noticeably while staying practical
            pix = doc[i].get_pixmap(matrix=fitz.Matrix(300 / 72, 300 / 72))
            png = pix.tobytes("png")
            pages_to_process.append((i, png))
        except Exception as e:
            print(f"[warn] Failed to render page {i} for OCR: {e}")

    # 2. Resolve the candidate model list ONCE for the whole batch (it's the same
    # for every page — no need to rebuild it per page) so we can spread pages
    # across DIFFERENT models instead of every page racing the same pinned model
    # first. Without this, N concurrent pages all hit model #1 simultaneously,
    # all trip its rate limit together, then all fall back to model #2 together,
    # etc. — lockstep contention, not real parallelism. Round-robin rotation lets
    # each group of concurrent calls start on different models.
    candidates = vision_ocr._candidate_models()

    # 3. Each page = one clean single-image OCR call — the SAME path a
    # standalone image upload uses. All pages are fired concurrently (up to
    # _OCR_MAX_CONCURRENT at once), rotated across different candidate models,
    # so wall-clock stays close to one call's latency without sacrificing
    # per-page transcription quality.
    def ocr_worker(item: tuple[int, bytes, int]) -> tuple[int, str]:
        idx, png_data, pos = item
        try:
            # allow_local=True: this is a page of a multi-page document, the
            # one case the rented-GPU local model is allowed to handle (when
            # classified as handwritten). Standalone image uploads deliberately
            # do NOT set this — see vision_ocr.ocr_image's docstring.
            text = vision_ocr.ocr_image(png_data, "image/png", models=candidates, rotate=pos, allow_local=True)
            return idx, text
        except Exception as e:
            print(f"[warn] OCR failed on page {idx}: {e}")
            return idx, ""

    items = [(i, png, pos) for pos, (i, png) in enumerate(pages_to_process)]
    with ThreadPoolExecutor(max_workers=_OCR_MAX_CONCURRENT) as executor:
        results = list(executor.map(ocr_worker, items))

    for idx, text in results:
        if text.strip():
            out[idx] = text
    return out


def ocr_image(data: bytes, mime: str = "image/png") -> str:
    """OCR a standalone image (PNG/JPG/…), including handwriting, via vision models."""
    from app.services import vision_ocr
    return vision_ocr.ocr_image(data, mime) if vision_ocr.available() else ""


def _zip_media_ocr(data: bytes, max_images: int = 20, min_bytes: int = 3000) -> str:
    """OCR images embedded inside a DOCX/PPTX (they live under `word/media/` or
    `ppt/media/`). This makes scanned or **handwritten** pictures pasted into an
    Office file searchable, just like a scanned PDF page or a standalone image
    upload. Uses the same model OCR path (`ocr_image`), so handwriting is
    handled. Tiny images (icons/logos below `min_bytes`) are
    skipped to avoid noise. Best-effort: returns '' if nothing is found or OCR is
    unavailable; never raises."""
    import zipfile
    out: list[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            count = 0
            for name in z.namelist():
                low = name.lower()
                if "/media/" not in low:
                    continue
                ext = low.rsplit(".", 1)[-1] if "." in low else ""
                if ext not in {"png", "jpg", "jpeg", "bmp", "tiff", "webp"}:
                    continue
                raw = z.read(name)
                if len(raw) < min_bytes:
                    continue
                mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
                text = ocr_image(raw, mime)
                if text and text.strip():
                    out.append(text.strip())
                count += 1
                if count >= max_images:
                    break
    except Exception as e:  # noqa: BLE001
        print(f"[warn] embedded-image OCR failed: {e}")
    return "\n\n".join(out)


def _docx(data: bytes) -> str:
    import docx
    d = docx.Document(io.BytesIO(data))
    lines = [p.text for p in d.paragraphs if p.text.strip()]
    for table in d.tables:
        for row in table.rows:
            lines.append(" | ".join(c.text for c in row.cells))
    # Handwritten / scanned images pasted into the document → OCR them in too.
    ocr = _zip_media_ocr(data)
    if ocr:
        lines.append("\n[Text from embedded handwritten/scanned images]")
        lines.append(ocr)
    return "\n".join(lines)


def _pptx(data: bytes) -> str:
    from pptx import Presentation
    prs = Presentation(io.BytesIO(data))
    lines = []
    for i, slide in enumerate(prs.slides, 1):
        lines.append(f"[Slide {i}]")
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    txt = "".join(r.text for r in para.runs)
                    if txt.strip():
                        lines.append(txt)
    # Handwritten / scanned pictures on the slides → OCR them in too.
    ocr = _zip_media_ocr(data)
    if ocr:
        lines.append("\n[Text from embedded handwritten/scanned images]")
        lines.append(ocr)
    return "\n".join(lines)


def _xlsx(data: bytes) -> str:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    lines = []
    for ws in wb.worksheets:
        lines.append(f"[Sheet: {ws.title}]")
        for row in ws.iter_rows(values_only=True):
            cells = [str(c) for c in row if c is not None]
            if cells:
                lines.append(" | ".join(cells))
    return "\n".join(lines)


def _csv(data: bytes) -> str:
    text = data.decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text))
    return "\n".join(" | ".join(row) for row in reader)


def extract_figures(filename: str, data: bytes, max_figures: int = 30,
                    min_bytes: int = 3000) -> list[dict]:
    """Pull embedded raster figures out of a document for the figure gallery
    (backlog §6.1). Returns a list of {"ext", "bytes", "page"} dicts. Tiny images
    (icons, bullets, logos) below `min_bytes` are skipped. Never raises — returns
    [] for unsupported types or on any parser error."""
    ext = _ext(filename)
    try:
        if ext == ".pdf":
            return _pdf_figures(data, max_figures, min_bytes)
        if ext in (".docx", ".pptx"):
            return _zip_media_figures(data, max_figures, min_bytes)
    except Exception as e:  # noqa: BLE001
        print(f"[warn] figure extraction failed for {filename!r}: {e}")
    return []


def _pdf_figures(data: bytes, max_figures: int, min_bytes: int) -> list[dict]:
    import fitz  # PyMuPDF
    figs: list[dict] = []
    seen: set[int] = set()
    with fitz.open(stream=data, filetype="pdf") as doc:
        for pno, page in enumerate(doc, 1):
            for img in page.get_images(full=True):
                xref = img[0]
                if xref in seen:
                    continue
                seen.add(xref)
                try:
                    info = doc.extract_image(xref)
                except Exception:
                    continue
                raw = info.get("image")
                if raw and len(raw) >= min_bytes:
                    figs.append({"ext": info.get("ext", "png"), "bytes": raw, "page": pno})
                if len(figs) >= max_figures:
                    return figs
    return figs


def _zip_media_figures(data: bytes, max_figures: int, min_bytes: int) -> list[dict]:
    """DOCX/PPTX are zip archives; embedded images live under word/media or
    ppt/media."""
    import zipfile
    figs: list[dict] = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in z.namelist():
            low = name.lower()
            if "/media/" not in low:
                continue
            ext = low.rsplit(".", 1)[-1] if "." in low else ""
            if ext not in {"png", "jpg", "jpeg", "gif", "bmp", "tiff", "webp"}:
                continue
            raw = z.read(name)
            if len(raw) >= min_bytes:
                figs.append({"ext": ext, "bytes": raw, "page": None})
            if len(figs) >= max_figures:
                break
    return figs


def chunk(text: str, size: int = 1200, overlap: int = 150) -> list[str]:
    """Split text into overlapping chunks on paragraph/sentence boundaries.

    Overlap preserves context across boundaries so a query that straddles two
    chunks still retrieves coherent passages.
    """
    text = (text or "").strip()
    if not text:
        return []
    paras = [p.strip() for p in text.split("\n") if p.strip()]
    chunks: list[str] = []
    buf = ""
    for para in paras:
        if len(buf) + len(para) + 1 <= size:
            buf = f"{buf}\n{para}" if buf else para
        else:
            if buf:
                chunks.append(buf)
            if len(para) <= size:
                buf = para
            else:  # a single huge paragraph — hard-split it
                for i in range(0, len(para), size - overlap):
                    chunks.append(para[i:i + size])
                buf = ""
    if buf:
        chunks.append(buf)
    return chunks
