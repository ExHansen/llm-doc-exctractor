"""Print formats and three ReportLab invoice templates."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

if TYPE_CHECKING:
    from docex.synthetic.generator import SyntheticInvoice

ID_MONTHS = (
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
)  # fmt: skip
EN_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _group(integer: int, sep: str) -> str:
    return f"{integer:,}".replace(",", sep)


def format_amount(value: Decimal, style: str) -> str:
    """Render money the way it is printed: `Rp 1.234.567`, `1.234.567,00`, `IDR 1,234,567`."""
    negative = value < 0
    value = abs(value).quantize(Decimal("0.01"))
    integer = int(value)
    cents = int((value - integer) * 100)
    if style == "rp_dot":
        text = "Rp " + _group(integer, ".") + (f",{cents:02d}" if cents else "")
    elif style == "dot_comma":
        text = _group(integer, ".") + f",{cents:02d}"
    elif style == "idr_comma":
        text = "IDR " + _group(integer, ",") + (f".{cents:02d}" if cents else "")
    else:
        raise ValueError(f"unknown number style: {style}")
    return ("-" + text) if negative else text


def format_date(d: date, fmt: str) -> str:
    if fmt == "long_id":
        return f"{d.day:02d} {ID_MONTHS[d.month - 1]} {d.year}"
    if fmt == "dmy_slash":
        return f"{d.day:02d}/{d.month:02d}/{d.year}"
    if fmt == "iso":
        return d.isoformat()
    if fmt == "short_en":
        return f"{d.day} {EN_MONTHS[d.month - 1]} {d.year}"
    raise ValueError(f"unknown date format: {fmt}")


def _qty(value: Decimal) -> str:
    return str(int(value)) if value == value.to_integral() else str(value)


def _rate(value: Decimal) -> str:
    return f"{int(value * 100)}%"


LABELS = {
    "modern": {
        "title": "INVOICE", "number": "Invoice No.", "date": "Invoice Date", "due": "Due Date",
        "from": "Bill From", "to": "Bill To", "npwp": "NPWP",
        "cols": ("#", "Description", "Qty", "Unit Price", "Amount"),
        "subtotal": "Subtotal", "discount": "Discount", "dpp": "Tax Base (DPP)",
        "dpp_other": "DPP Nilai Lain (11/12)", "tax": "VAT (PPN {rate})", "total": "TOTAL",
        "footer": "Thank you for your business.",
    },
    "klasik": {
        "title": "FAKTUR", "number": "No. Faktur", "date": "Tanggal", "due": "Jatuh Tempo",
        "from": "Penjual", "to": "Kepada Yth.", "npwp": "NPWP",
        "cols": ("No", "Uraian", "Qty", "Harga Satuan", "Jumlah"),
        "subtotal": "Subtotal", "discount": "Diskon", "dpp": "DPP",
        "dpp_other": "DPP Nilai Lain", "tax": "PPN {rate}", "total": "Total",
        "footer": "Hormat kami,",
    },
    "minimal": {
        "title": "Invoice / Faktur", "number": "Nomor", "date": "Date", "due": "Due",
        "from": "From", "to": "To", "npwp": "NPWP",
        "cols": ("", "Item", "Qty", "Price", "Total"),
        "subtotal": "Sub Total", "discount": "Potongan", "dpp": "DPP",
        "dpp_other": "DPP Nilai Lain", "tax": "PPN {rate}", "total": "Grand Total",
        "footer": "",
    },
}  # fmt: skip

ACCENT = {"modern": colors.HexColor("#1F4E79"), "klasik": colors.black, "minimal": colors.grey}


def _party(name: str, address: str, npwp: str | None, label: str, style) -> list:
    lines = [f"<b>{escape(name)}</b>", escape(address)]
    if npwp:
        lines.append(f"{label}: {escape(npwp)}")
    return [Paragraph("<br/>".join(lines), style)]


def render_invoice_pdf(si: SyntheticInvoice, path: Path) -> None:
    """Draw one A4 page with every field of the invoice, using the invoice's layout."""
    inv, layout = si.invoice, si.layout
    lab = LABELS[layout.template]
    accent = ACCENT[layout.template]
    amt = lambda v: format_amount(v, layout.number_style)  # noqa: E731
    styles = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=styles["Normal"], fontSize=9, leading=12)
    title_align = TA_CENTER if layout.template == "klasik" else TA_RIGHT
    title = ParagraphStyle(
        "title", parent=styles["Title"], fontSize=20, textColor=accent, alignment=title_align
    )
    story: list = [Paragraph(escape(lab["title"]), title), Spacer(1, 4 * mm)]

    meta_rows = [
        [lab["number"], inv.invoice_number],
        [lab["date"], format_date(inv.invoice_date, layout.date_format)],
    ]
    if inv.due_date is not None:
        meta_rows.append([lab["due"], format_date(inv.due_date, layout.date_format)])
    meta = Table(meta_rows, colWidths=[32 * mm, 55 * mm], hAlign="RIGHT")
    meta.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 9),
                              ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold")]))  # fmt: skip

    seller = _party(inv.seller_name, layout.seller_address, inv.seller_npwp, lab["npwp"], body)
    buyer = _party(inv.buyer_name, layout.buyer_address, inv.buyer_npwp, lab["npwp"], body)
    parties = Table(
        [[Paragraph(f"<b>{lab['from']}</b>", body), Paragraph(f"<b>{lab['to']}</b>", body)],
         [seller, buyer]],
        colWidths=[85 * mm, 85 * mm],
    )  # fmt: skip
    parties.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [meta, Spacer(1, 5 * mm), parties, Spacer(1, 6 * mm)]

    rows = [list(lab["cols"])]
    for i, it in enumerate(inv.line_items, start=1):
        rows.append([str(i), Paragraph(escape(it.description), body), _qty(it.quantity),
                     amt(it.unit_price), amt(it.amount)])  # fmt: skip
    items = Table(rows, colWidths=[10 * mm, 78 * mm, 14 * mm, 34 * mm, 34 * mm], repeatRows=1)
    item_style = [
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    if layout.template == "modern":
        item_style += [("BACKGROUND", (0, 0), (-1, 0), accent),
                       ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                       ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9DB3C8"))]  # fmt: skip
    elif layout.template == "klasik":
        item_style += [("BOX", (0, 0), (-1, -1), 1, colors.black),
                       ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.black)]  # fmt: skip
    else:
        item_style += [("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.grey)]
    items.setStyle(TableStyle(item_style))
    story += [items, Spacer(1, 4 * mm)]

    dpp_label = lab["dpp_other"] if si.tax_scheme == "dpp_nilai_lain" else lab["dpp"]
    totals_rows = [
        [lab["subtotal"], amt(inv.subtotal)],
        [lab["discount"], amt(inv.discount)],
        [dpp_label, amt(inv.tax_base)],
        [lab["tax"].format(rate=_rate(inv.tax_rate)), amt(inv.tax_amount)],
        [lab["total"], amt(inv.total)],
    ]
    totals = Table(totals_rows, colWidths=[45 * mm, 40 * mm], hAlign="RIGHT")
    totals.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, accent),
    ]))  # fmt: skip
    story += [totals, Spacer(1, 10 * mm)]
    if lab["footer"]:
        story.append(Paragraph(escape(lab["footer"]), body))
        if layout.template == "klasik":
            story += [Spacer(1, 14 * mm), Paragraph(f"<b>{escape(inv.seller_name)}</b>", body)]

    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm, title=f"{lab['title']} {inv.invoice_number}",
    )  # fmt: skip
    doc.build(story)
