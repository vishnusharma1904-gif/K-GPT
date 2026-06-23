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

SUPPORTED = {".pdf", ".docx", ".pptx", ".xlsx", ".xls", ".csv", ".txt", ".md"}
MAX_BYTES = 15 * 1024 * 1024  # 15 MB guard


class ExtractError(Exception):
    """Raised with a user-safe message when extraction can't proceed."""


def _ext(filename: str) -> str:
    return ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""


def extract_text(filename: str, data: bytes) -> str:
    """Return the plain text of an uploaded file. Raises ExtractError on failure."""
    if len(data) > MAX_BYTES:
        raise ExtractError("File is too large (max 15 MB).")
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
        return data.decode("utf-8", errors="replace")  # .txt / .md
    except ExtractError:
        raise
    except Exception as e:  # noqa: BLE001
        raise ExtractError(f"Couldn't read this file ({type(e).__name__}).") from e


def _pdf(data: bytes) -> str:
    import fitz  # PyMuPDF
    parts = []
    with fitz.open(stream=data, filetype="pdf") as doc:
        for page in doc:
            parts.append(page.get_text())
    return "\n".join(parts)


def _docx(data: bytes) -> str:
    import docx
    d = docx.Document(io.BytesIO(data))
    lines = [p.text for p in d.paragraphs if p.text.strip()]
    for table in d.tables:
        for row in table.rows:
            lines.append(" | ".join(c.text for c in row.cells))
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
