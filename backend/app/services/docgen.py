"""Document generation — turn an assistant reply (Markdown, optionally with
fenced ```chart specs) into a real downloadable .pdf / .docx / .xlsx, with proper
tables and rendered charts/graphs embedded.

Pipeline:
  parse_markdown(text)  -> a list of typed blocks
  build_pdf / build_docx / build_xlsx(title, blocks) -> bytes

Charts: a fenced ```chart block carrying the same JSON the chat UI renders
  {"type":"bar|line|pie","title":"...","x":[...],
   "series":[{"name":"A","data":[1,2,3]}]}
is rendered to PNG (matplotlib, headless Agg) for PDF/DOCX and to a NATIVE chart
for XLSX. Everything degrades gracefully — a bad chart spec becomes a caption, a
missing lib is skipped — so export never hard-fails on one block.
"""
from __future__ import annotations

import html
import io
import json
import re
from typing import Any

# ============================================================================
# Markdown → blocks
# ============================================================================
_FENCE = re.compile(r"^```(\w*)\s*$")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_LISTITEM = re.compile(r"^\s*([-*+]|\d+\.)\s+(.*)$")
_SEP_ROW = re.compile(r"^\s*\|?[\s:|\-]+\|?\s*$")


def _strip_inline(text: str) -> str:
    """Drop Markdown emphasis markers for clean plain text (tables, lists, xlsx)."""
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    s = re.sub(r"`(.+?)`", r"\1", s)
    s = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"\1", s)
    s = re.sub(r"\[(.+?)\]\((.+?)\)", r"\1", s)   # [text](url) -> text
    return s.strip()


def _row_cells(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [_strip_inline(c.strip()) for c in s.split("|")]


def parse_markdown(md: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    lines = (md or "").split("\n")
    n = len(lines)
    i = 0
    para: list[str] = []
    listbuf: list[str] = []
    list_ordered: bool | None = None

    def flush_para():
        nonlocal para
        if para:
            blocks.append({"type": "para", "text": _strip_inline(" ".join(p.strip() for p in para))})
            para = []

    def flush_list():
        nonlocal listbuf, list_ordered
        if listbuf:
            blocks.append({"type": "list", "ordered": bool(list_ordered), "items": listbuf})
            listbuf = []
            list_ordered = None

    while i < n:
        line = lines[i]
        fence = _FENCE.match(line.strip())
        if fence:
            flush_para(); flush_list()
            lang = (fence.group(1) or "").lower()
            body: list[str] = []
            i += 1
            while i < n and not _FENCE.match(lines[i].strip()):
                body.append(lines[i]); i += 1
            i += 1  # consume closing fence
            text = "\n".join(body)
            if lang == "chart":
                try:
                    spec = json.loads(text)
                except Exception:
                    spec = None
                blocks.append({"type": "chart", "spec": spec} if spec else {"type": "code", "text": text})
            else:
                blocks.append({"type": "code", "text": text})
            continue

        # Markdown table: a pipe row followed by a separator row.
        if (line.strip().startswith("|") and i + 1 < n
                and "|" in lines[i + 1] and "-" in lines[i + 1]
                and _SEP_ROW.match(lines[i + 1])):
            flush_para(); flush_list()
            header = _row_cells(line)
            i += 2
            rows: list[list[str]] = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(_row_cells(lines[i])); i += 1
            blocks.append({"type": "table", "header": header, "rows": rows})
            continue

        h = _HEADING.match(line)
        if h:
            flush_para(); flush_list()
            blocks.append({"type": "heading", "level": len(h.group(1)),
                           "text": _strip_inline(h.group(2).strip())})
            i += 1
            continue

        li = _LISTITEM.match(line)
        if li:
            flush_para()
            ordered = bool(re.match(r"\d+\.", li.group(1)))
            if list_ordered is None:
                list_ordered = ordered
            listbuf.append(_strip_inline(li.group(2).strip()))
            i += 1
            continue

        if not line.strip():
            flush_para(); flush_list()
            i += 1
            continue

        flush_list()
        para.append(line)
        i += 1

    flush_para(); flush_list()
    return blocks


# ============================================================================
# Chart rendering (matplotlib → PNG) for PDF / DOCX
# ============================================================================
def render_chart_png(spec: dict) -> bytes | None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return None
    t = (spec.get("type") or "bar").lower()
    x = [str(v) for v in (spec.get("x") or [])]
    series = spec.get("series") or []
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    try:
        if t == "pie":
            data = [_num(v) for v in ((series[0].get("data") if series else []) or [])]
            ax.pie(data, labels=x or None, autopct="%1.1f%%", startangle=90)
            ax.axis("equal")
        elif t == "line":
            idx = list(range(len(x)))
            for s in series:
                ax.plot(idx, [_num(v) for v in s.get("data", [])], marker="o", label=s.get("name"))
            ax.set_xticks(idx); ax.set_xticklabels(x, rotation=0)
            if any(s.get("name") for s in series):
                ax.legend()
        else:  # bar (grouped)
            ns = max(1, len(series))
            width = 0.8 / ns
            idx = list(range(len(x)))
            for j, s in enumerate(series):
                ax.bar([k + j * width for k in idx], [_num(v) for v in s.get("data", [])],
                       width=width, label=s.get("name"))
            ax.set_xticks([k + width * (ns - 1) / 2 for k in idx])
            ax.set_xticklabels(x, rotation=0)
            if any(s.get("name") for s in series):
                ax.legend()
        if spec.get("title"):
            ax.set_title(spec["title"])
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=140)
        return buf.getvalue()
    except Exception:
        return None
    finally:
        try:
            import matplotlib.pyplot as plt
            plt.close(fig)
        except Exception:
            pass


def _num(v: Any) -> float:
    try:
        return float(str(v).replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return 0.0


# ============================================================================
# DOCX
# ============================================================================
def build_docx(title: str, blocks: list[dict]) -> bytes:
    from docx import Document
    from docx.shared import Inches, Pt

    doc = Document()
    if title:
        doc.add_heading(title, level=0)
    for b in blocks:
        bt = b["type"]
        if bt == "heading":
            doc.add_heading(b["text"], level=min(max(b["level"], 1), 4))
        elif bt == "para":
            _docx_runs(doc.add_paragraph(), b["text"])
        elif bt == "list":
            style = "List Number" if b["ordered"] else "List Bullet"
            for it in b["items"]:
                doc.add_paragraph(it, style=style)
        elif bt == "table":
            _docx_table(doc, b)
        elif bt == "code":
            p = doc.add_paragraph()
            r = p.add_run(b["text"])
            r.font.name = "Courier New"
            r.font.size = Pt(9)
        elif bt == "chart":
            png = render_chart_png(b["spec"]) if b.get("spec") else None
            if png:
                doc.add_picture(io.BytesIO(png), width=Inches(6))
            elif b.get("spec", {}).get("title"):
                doc.add_paragraph(b["spec"]["title"])
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _docx_runs(paragraph, text: str) -> None:
    """Render **bold** segments as bold runs; rest plain."""
    for part in re.split(r"(\*\*.+?\*\*)", text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            paragraph.add_run(part[2:-2]).bold = True
        else:
            paragraph.add_run(_strip_inline(part))


def _docx_table(doc, b: dict) -> None:
    header = b["header"]
    rows = b["rows"]
    ncols = max([len(header)] + [len(r) for r in rows] or [1])
    table = doc.add_table(rows=1, cols=ncols)
    try:
        table.style = "Light Grid Accent 1"
    except Exception:
        table.style = "Table Grid"
    hdr = table.rows[0].cells
    for c in range(ncols):
        cell = hdr[c]
        cell.text = header[c] if c < len(header) else ""
        for p in cell.paragraphs:
            for r in p.runs:
                r.bold = True
    for row in rows:
        cells = table.add_row().cells
        for c in range(ncols):
            cells[c].text = str(row[c]) if c < len(row) else ""


# ============================================================================
# PDF (reportlab)
# ============================================================================
def _rl_inline(text: str) -> str:
    s = html.escape(text, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"`(.+?)`", r"<font face='Courier'>\1</font>", s)
    s = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", s)
    return s


def build_pdf(title: str, blocks: list[dict]) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                    TableStyle, Image)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=0.7 * inch,
                            bottomMargin=0.7 * inch, leftMargin=0.7 * inch,
                            rightMargin=0.7 * inch, title=title)
    styles = getSampleStyleSheet()
    story: list = []
    if title:
        story.append(Paragraph(_rl_inline(title), styles["Title"]))
        story.append(Spacer(1, 10))

    for b in blocks:
        bt = b["type"]
        if bt == "heading":
            name = f"Heading{min(max(b['level'], 1), 4)}"
            story.append(Paragraph(_rl_inline(b["text"]), styles.get(name, styles["Heading2"])))
        elif bt == "para":
            story.append(Paragraph(_rl_inline(b["text"]), styles["BodyText"]))
        elif bt == "list":
            for it in b["items"]:
                prefix = "• " if not b["ordered"] else ""
                story.append(Paragraph(prefix + _rl_inline(it), styles["BodyText"]))
        elif bt == "table":
            data = [b["header"]] + b["rows"]
            ncols = max(len(r) for r in data) if data else 1
            cell = lambda c: Paragraph(_rl_inline(str(c)), styles["BodyText"])  # noqa: E731
            grid = [[cell(row[c]) if c < len(row) else cell("") for c in range(ncols)] for row in data]
            tbl = Table(grid, repeatRows=1)
            tbl.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f9d72")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4faf7")]),
            ]))
            story.append(tbl)
            story.append(Spacer(1, 8))
        elif bt == "chart":
            png = render_chart_png(b["spec"]) if b.get("spec") else None
            if png:
                story.append(Image(io.BytesIO(png), width=6 * inch, height=3.4 * inch))
                story.append(Spacer(1, 8))
        elif bt == "code":
            story.append(Paragraph("<font face='Courier'>"
                                   + html.escape(b["text"], quote=False).replace("\n", "<br/>")
                                   + "</font>", styles["BodyText"]))
        story.append(Spacer(1, 4))

    doc.build(story)
    return buf.getvalue()


# ============================================================================
# XLSX (openpyxl, native charts)
# ============================================================================
def build_xlsx(title: str, blocks: list[dict]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.chart import BarChart, LineChart, PieChart, Reference
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = "Report"
    r = 1
    if title:
        c = ws.cell(row=r, column=1, value=title)
        c.font = Font(bold=True, size=14)
        r += 2

    t_no = 0
    c_no = 0
    for b in blocks:
        bt = b["type"]
        if bt == "heading":
            cell = ws.cell(row=r, column=1, value=b["text"])
            cell.font = Font(bold=True, size=12)
            r += 1
        elif bt == "para":
            ws.cell(row=r, column=1, value=b["text"])
            r += 1
        elif bt == "list":
            for it in b["items"]:
                ws.cell(row=r, column=1, value=f"• {it}")
                r += 1
        elif bt == "table":
            t_no += 1
            tws = wb.create_sheet(f"Table {t_no}")
            tws.append(b["header"])
            for cell in tws[1]:
                cell.font = Font(bold=True)
            for row in b["rows"]:
                tws.append([_maybe_num(v) for v in row])
            ws.cell(row=r, column=1, value=f"→ Table {t_no} (sheet)")
            r += 1
        elif bt == "chart" and b.get("spec"):
            c_no += 1
            made = _xlsx_chart(wb, b["spec"], c_no, BarChart, LineChart, PieChart, Reference, Font)
            ws.cell(row=r, column=1, value=f"→ {made} (sheet)" if made else (b["spec"].get("title") or "chart"))
            r += 1
        r += 1

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _maybe_num(v: Any):
    s = str(v).strip()
    try:
        f = float(s.replace(",", ""))
        return int(f) if f.is_integer() else f
    except (TypeError, ValueError):
        return v


def _xlsx_chart(wb, spec, idx, BarChart, LineChart, PieChart, Reference, Font) -> str | None:
    name = f"Chart {idx}"
    ws = wb.create_sheet(name)
    x = [str(v) for v in (spec.get("x") or [])]
    series = spec.get("series") or []
    if not x or not series:
        return None
    # header: category + one column per series
    ws.cell(row=1, column=1, value="Category").font = Font(bold=True)
    for j, s in enumerate(series):
        ws.cell(row=1, column=2 + j, value=s.get("name") or f"Series {j + 1}").font = Font(bold=True)
    for i, label in enumerate(x):
        ws.cell(row=2 + i, column=1, value=label)
        for j, s in enumerate(series):
            data = s.get("data") or []
            ws.cell(row=2 + i, column=2 + j, value=_num(data[i]) if i < len(data) else None)

    t = (spec.get("type") or "bar").lower()
    chart = PieChart() if t == "pie" else (LineChart() if t == "line" else BarChart())
    chart.title = spec.get("title") or name
    cats = Reference(ws, min_col=1, min_row=2, max_row=1 + len(x))
    if t == "pie":
        data_ref = Reference(ws, min_col=2, min_row=1, max_row=1 + len(x))
        chart.add_data(data_ref, titles_from_data=True)
    else:
        data_ref = Reference(ws, min_col=2, max_col=1 + len(series), min_row=1, max_row=1 + len(x))
        chart.add_data(data_ref, titles_from_data=True)
    chart.set_categories(cats)
    chart.height = 9
    chart.width = 16
    from openpyxl.utils import get_column_letter
    ws.add_chart(chart, f"{get_column_letter(len(series) + 3)}2")
    return name
