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

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}
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


def _pdf(data: bytes) -> str:
    import fitz  # PyMuPDF
    parts: list[str] = []
    needs_ocr: list[int] = []
    with fitz.open(stream=data, filetype="pdf") as doc:
        for i, page in enumerate(doc):
            txt = page.get_text()
            parts.append(txt)
            if len((txt or "").strip()) < _OCR_MIN_CHARS_PER_PAGE:
                needs_ocr.append(i)

        # Scanned / image-only pages have no digital text layer. OCR them so the
        # content is still searchable (backlog §6.4). Best-effort: if Tesseract /
        # its Python binding isn't installed, we keep whatever text we have.
        if needs_ocr:
            ocr = _ocr_pdf_pages(doc, needs_ocr)
            for i, text in ocr.items():
                if text.strip():
                    parts[i] = text
    return "\n".join(parts)


def _tesseract_image(data: bytes) -> str:
    """Tesseract OCR on raw image bytes. '' if unavailable. Good for printed
    scans, poor on handwriting (hence the vision-model path in ocr_image)."""
    try:
        import io as _io
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore
        return pytesseract.image_to_string(Image.open(_io.BytesIO(data)))
    except Exception as e:  # noqa: BLE001
        print(f"[warn] Tesseract OCR unavailable/failed: {e}")
        return ""


def _ocr_pdf_pages(doc, page_indexes: list[int]) -> dict[int, str]:
    """OCR the given PDF pages. Returns {page_index: text}. For each page we try
    the cheap vision model first (90%+ on handwriting) and fall back to Tesseract
    (printed scans) when vision OCR isn't configured. Never raises."""
    from app.services import vision_ocr
    use_vision = vision_ocr.available()
    try:
        import fitz  # PyMuPDF
    except Exception:
        return {}
    out: dict[int, str] = {}
    for i in page_indexes:
        try:
            # 200 DPI render: enough for both engines, keeps the vision payload small.
            pix = doc[i].get_pixmap(matrix=fitz.Matrix(200 / 72, 200 / 72))
            png = pix.tobytes("png")
            text = vision_ocr.ocr_image(png, "image/png") if use_vision else ""
            if not text.strip():
                text = _tesseract_image(png)
            if text.strip():
                out[i] = text
        except Exception as e:  # noqa: BLE001
            print(f"[warn] OCR failed on page {i}: {e}")
    return out


def ocr_image(data: bytes, mime: str = "image/png") -> str:
    """OCR a standalone image (PNG/JPG/…), including handwriting. Tries the cheap
    vision model first, then Tesseract. Best-effort; '' if nothing is available."""
    from app.services import vision_ocr
    text = vision_ocr.ocr_image(data, mime) if vision_ocr.available() else ""
    if not text.strip():
        text = _tesseract_image(data)
    return text


def _zip_media_ocr(data: bytes, max_images: int = 20, min_bytes: int = 3000) -> str:
    """OCR images embedded inside a DOCX/PPTX (they live under `word/media/` or
    `ppt/media/`). This makes scanned or **handwritten** pictures pasted into an
    Office file searchable, just like a scanned PDF page or a standalone image
    upload. Uses the same vision-model-first → Tesseract path (`ocr_image`), so
    handwriting is handled. Tiny images (icons/logos below `min_bytes`) are
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
