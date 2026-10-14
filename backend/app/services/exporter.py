"""Multi-format export: CSV, XLSX, PDF, PNG, JPG, JSON, HTML.

Every audience view tabularizes to (title, headers, rows); each format
renderer consumes that uniform shape plus run metrics.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

FORMATS = ["csv", "xlsx", "pdf", "png", "jpg", "json", "html"]

_MEDIA = {
    "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "json": "application/json",
    "html": "text/html",
}


def tabularize(view_data: Dict[str, Any]) -> Tuple[str, List[str], List[List[str]]]:
    """View JSON -> (title, headers, rows)."""
    view = view_data.get("view", "master")
    if view == "master":
        return (
            view_data.get("title", "Master Timetable"),
            view_data.get("headers", []),
            [[str(c) for c in r] for r in view_data.get("rows", [])],
        )
    if view == "teacher":
        rows = [
            [t["name"], s["day_slot"], s["course"], s["room"]]
            for t in view_data.get("teachers", [])
            for s in t["sessions"]
        ]
        return ("Teacher Schedules", ["Teacher", "Day / Slot", "Course", "Room"], rows)
    if view == "student":
        rows = [
            [g["course"], g["teacher"], s.get("meeting", ""), s["day_slot"], s["room"]]
            for g in view_data.get("courses", [])
            for s in g["sessions"]
        ]
        return ("Student Schedules", ["Course", "Teacher", "Meeting", "Day / Slot", "Room"], rows)
    if view == "staff":
        rows = [
            [s["slot"], str(s["concurrent_classes"]), ", ".join(s["teachers_busy"]),
             ", ".join(s["rooms_in_use"]), str(s["free_rooms"])]
            for s in view_data.get("slots", [])
        ]
        return ("Support Staff Schedule",
                ["Slot", "Concurrent classes", "Teachers busy", "Rooms in use", "Free rooms"], rows)
    # canteen
    rows = [
        [s["slot"], str(s["concurrent_classes"])]
        for s in view_data.get("slots", [])
    ]
    return ("Canteen Schedule", ["Slot", "Concurrent classes (demand proxy)"], rows)


def to_csv(title: str, headers: List[str], rows: List[List[str]]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([title])
    w.writerow(headers)
    w.writerows(rows)
    return buf.getvalue().encode("utf-8")


def to_json(view: str, title: str, headers: List[str],
            rows: List[List[str]], metrics: Dict[str, Any]) -> bytes:
    return json.dumps(
        {"view": view, "title": title, "headers": headers, "rows": rows,
         "metrics": metrics, "exported_at": datetime.now().isoformat()},
        indent=2,
    ).encode("utf-8")


def to_html(title: str, headers: List[str], rows: List[List[str]],
            metrics: Dict[str, Any]) -> bytes:
    def cell(c: str) -> str:
        return str(c).replace("&", "&amp;").replace("<", "&lt;").replace("\n", "<br/>")

    body = "".join(
        "<tr>" + "".join(f"<td>{cell(c)}</td>" for c in r) + "</tr>" for r in rows
    )
    head = "".join(f"<th>{cell(h)}</th>" for h in headers)
    metrics_html = "".join(f"<p><b>{k}:</b> {v}</p>" for k, v in metrics.items())
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>{title}</title>
<style>body{{font-family:Arial,sans-serif;margin:20px}}h1{{color:#1f4e78}}
table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #999;padding:8px;text-align:center}}
th{{background:#4472C4;color:#fff}}tr:nth-child(even){{background:#f2f2f2}}</style>
</head><body><h1>{title}</h1><table><tr>{head}</tr>{body}</table>
<div><h3>Metrics</h3>{metrics_html}</div></body></html>""".encode("utf-8")


def to_xlsx(title: str, headers: List[str], rows: List[List[str]],
            metrics: Dict[str, Any]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    wb = Workbook()
    ws = wb.active
    ws.title = "Schedule"
    thin = Border(*[Side(style="thin")] * 4)
    wrap = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.append([title])
    ws.append(headers)
    for r in rows:
        ws.append(r)
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=len(headers)):
        for cell in row:
            cell.alignment = wrap
            cell.border = thin
    for cell in ws[2]:
        cell.fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        cell.font = Font(color="FFFFFF", bold=True)
    for i, h in enumerate(headers, start=1):
        width = max([len(str(h))] + [len(str(r[i - 1])) for r in rows] + [0])
        ws.column_dimensions[ws.cell(row=2, column=i).column_letter].width = min(width + 4, 45)
    m = wb.create_sheet("Metrics")
    for k, v in metrics.items():
        m.append([k, v])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def to_pdf(title: str, headers: List[str], rows: List[List[str]],
           metrics: Dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    def cell(text: str) -> Paragraph:
        safe = str(text).replace("&", "&amp;").replace("<", "&lt;").replace("\n", "<br/>")
        return Paragraph(safe, getSampleStyleSheet()["Normal"])

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4))
    elements = [Paragraph(title, ParagraphStyle("t", fontSize=20, textColor=colors.HexColor("#1f4e78"))),
                Spacer(1, 12)]
    data = [[cell(h) for h in headers]] + [[cell(c) for c in r] for r in rows]
    ncols = max(len(headers), 1)
    table = Table(data, colWidths=[(10 * inch) / ncols] * ncols, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4472C4")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
    ]))
    elements += [table, Spacer(1, 14),
                 Paragraph("<br/>".join(f"<b>{k}:</b> {v}" for k, v in metrics.items()),
                           getSampleStyleSheet()["Normal"])]
    doc.build(elements)
    return buf.getvalue()


def to_image(title: str, headers: List[str], rows: List[List[str]],
             fmt: str = "png") -> bytes:
    from PIL import Image, ImageDraw, ImageFont

    def font(size: int, bold: bool = False):
        name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
        for path in (f"/usr/share/fonts/truetype/dejavu/{name}", name):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
        return ImageFont.load_default()

    cw, chh, margin, th = 220, 64, 20, 56
    ncols = max(len(headers), 1)
    img = Image.new("RGB", (ncols * cw + 2 * margin, th + (len(rows) + 1) * chh + 2 * margin), "white")
    d = ImageDraw.Draw(img)
    f_title, f_head, f_cell = font(20, True), font(12, True), font(11)
    d.text((margin, 12), title[:80], fill="black", font=f_title)
    y0 = th + margin
    for ci, h in enumerate(headers):
        x = margin + ci * cw
        d.rectangle([(x, y0), (x + cw, y0 + chh)], fill="#4472C4", outline="black")
        d.text((x + 6, y0 + 8), str(h)[:28], fill="white", font=f_head)
    for ri, r in enumerate(rows):
        y = y0 + (ri + 1) * chh
        fill = "#f2f2f2" if ri % 2 else "white"
        for ci in range(ncols):
            x = margin + ci * cw
            d.rectangle([(x, y), (x + cw, y + chh)], fill=fill, outline="black")
            txt = str(r[ci]).replace("\n", " / ")[:52] if ci < len(r) else ""
            d.text((x + 6, y + 8), txt, fill="black", font=f_cell)
    buf = io.BytesIO()
    img.save(buf, "JPEG" if fmt == "jpg" else "PNG")
    return buf.getvalue()


def export_view(db, run_id: int, view: str, fmt: str,
                teacher_only: Optional[str] = None) -> Tuple[bytes, str, str]:
    """Render one view in one format -> (content, media_type, filename)."""
    from app.services.views import build_view, run_metrics

    fmt = fmt.lower()
    if fmt not in FORMATS:
        raise ValueError(f"unsupported format '{fmt}'; choose from {FORMATS}")
    view_data = build_view(db, run_id, view, teacher_only=teacher_only)
    metrics = run_metrics(db, run_id)
    title, headers, rows = tabularize(view_data)
    if fmt == "csv":
        content = to_csv(title, headers, rows)
    elif fmt == "json":
        content = to_json(view, title, headers, rows, metrics)
    elif fmt == "html":
        content = to_html(title, headers, rows, metrics)
    elif fmt == "xlsx":
        content = to_xlsx(title, headers, rows, metrics)
    elif fmt == "pdf":
        content = to_pdf(title, headers, rows, metrics)
    else:
        content = to_image(title, headers, rows, fmt)
    return content, _MEDIA[fmt], f"timetable_{run_id}_{view}.{fmt}"
