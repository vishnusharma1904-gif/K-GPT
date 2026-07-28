"""Document export — turn an assistant reply into a real downloadable file.

POST /api/export  { content, format: pdf|docx|xlsx, title? }  → the file stream.
Markdown tables become real tables and fenced ```chart specs become rendered
graphs (native charts in xlsx; PNG images in pdf/docx). Auth-gated.
"""
from __future__ import annotations

import io
import re

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.security import current_user
from app.services import docgen

router = APIRouter(prefix="/api/export", tags=["export"])

_CONTENT_TYPE = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


class ExportReq(BaseModel):
    content: str = Field(min_length=1, max_length=200_000)
    format: str
    title: str | None = Field(default=None, max_length=200)


@router.post("")
async def export(req: ExportReq, _: dict = Depends(current_user)):
    fmt = (req.format or "").lower().strip()
    if fmt not in _CONTENT_TYPE:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "format must be pdf, docx or xlsx")

    title = (req.title or "K-GPT Document").strip()[:120] or "K-GPT Document"
    blocks = docgen.parse_markdown(req.content)
    try:
        if fmt == "pdf":
            data = docgen.build_pdf(title, blocks)
        elif fmt == "docx":
            data = docgen.build_docx(title, blocks)
        else:
            data = docgen.build_xlsx(title, blocks)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            f"Could not generate {fmt.upper()}: {e}")

    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", title).strip("_")[:40] or "document"
    headers = {"Content-Disposition": f'attachment; filename="{safe}.{fmt}"'}
    return StreamingResponse(io.BytesIO(data), media_type=_CONTENT_TYPE[fmt], headers=headers)
