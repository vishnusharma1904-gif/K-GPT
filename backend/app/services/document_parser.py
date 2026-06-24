"""Document parser — extracts raw text from various file formats.

Supported formats:
  - PDF: PyMuPDF (fitz)
  - DOCX: python-docx
  - PPTX: python-pptx
  - XLSX: openpyxl
  - TXT, MD, CSV: plain text

This runs inside the async worker (consumed from RabbitMQ) so it never
blocks the API request.
"""
from __future__ import annotations

import io
from pathlib import Path

def parse_file(file_path: str | Path, mime_type: str = "") -> str:
    """Read a file from disk and extract its text."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    ext = path.suffix.lower()
    
    if ext == ".pdf" or mime_type == "application/pdf":
        return _parse_pdf(path)
    elif ext == ".docx" or "wordprocessingml" in mime_type:
        return _parse_docx(path)
    elif ext == ".pptx" or "presentationml" in mime_type:
        return _parse_pptx(path)
    elif ext == ".xlsx" or "spreadsheetml" in mime_type:
        return _parse_xlsx(path)
    elif ext in (".txt", ".md", ".csv", ".json") or "text/" in mime_type:
        # Fallback for plain text
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # Fallback to latin-1 if utf-8 fails
            return path.read_text(encoding="latin-1")
    else:
        raise ValueError(f"Unsupported file type: {ext} ({mime_type})")


def _parse_pdf(path: Path) -> str:
    """Extract text from a PDF using PyMuPDF."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return "[PDF parsing requires PyMuPDF (fitz)]"
    
    text_blocks = []
    try:
        doc = fitz.open(path)
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            if text.strip():
                text_blocks.append(f"--- Page {page_num + 1} ---\n{text}")
        doc.close()
    except Exception as e:
        print(f"[warn] PDF parse failed for {path}: {e}")
        
    return "\n\n".join(text_blocks)


def _parse_docx(path: Path) -> str:
    """Extract text from a DOCX file using python-docx."""
    try:
        import docx
    except ImportError:
        return "[DOCX parsing requires python-docx]"
        
    try:
        doc = docx.Document(path)
        return "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
    except Exception as e:
        print(f"[warn] DOCX parse failed for {path}: {e}")
        return ""


def _parse_pptx(path: Path) -> str:
    """Extract text from a PPTX file using python-pptx."""
    try:
        from pptx import Presentation
    except ImportError:
        return "[PPTX parsing requires python-pptx]"
        
    text_blocks = []
    try:
        prs = Presentation(path)
        for i, slide in enumerate(prs.slides):
            slide_text = []
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text.strip():
                    slide_text.append(shape.text.strip())
            if slide_text:
                text_blocks.append(f"--- Slide {i + 1} ---\n" + "\n".join(slide_text))
    except Exception as e:
        print(f"[warn] PPTX parse failed for {path}: {e}")
        
    return "\n\n".join(text_blocks)


def _parse_xlsx(path: Path) -> str:
    """Extract text from an XLSX file using openpyxl. Converts sheets to CSV-like text."""
    try:
        import openpyxl
    except ImportError:
        return "[XLSX parsing requires openpyxl]"
        
    text_blocks = []
    try:
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        for sheet_name in wb.sheetnames:
            sheet = wb[sheet_name]
            sheet_text = [f"--- Sheet: {sheet_name} ---"]
            for row in sheet.iter_rows(values_only=True):
                # Filter out completely empty rows
                if not any(row):
                    continue
                row_str = " | ".join([str(cell).strip() for cell in row if cell is not None])
                sheet_text.append(row_str)
            text_blocks.append("\n".join(sheet_text))
        wb.close()
    except Exception as e:
        print(f"[warn] XLSX parse failed for {path}: {e}")
        
    return "\n\n".join(text_blocks)
