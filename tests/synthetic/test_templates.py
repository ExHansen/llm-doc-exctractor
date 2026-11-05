import random
from datetime import date
from decimal import Decimal

import pypdfium2
import pytest

from docex.imaging import render_first_page
from docex.synthetic.catalog import DATE_FORMATS, NUMBER_STYLES
from docex.synthetic.degrade import degrade_pdf
from docex.synthetic.generator import make_invoice
from docex.synthetic.templates import format_amount, format_date, render_invoice_pdf
from docex.validation.normalize import parse_date, parse_number


@pytest.mark.parametrize("style", NUMBER_STYLES)
@pytest.mark.parametrize("value", ["0.00", "500.00", "1234567.00", "91667.00"])
def test_amount_roundtrip(style, value):
    assert parse_number(format_amount(Decimal(value), style)) == Decimal(value)


def test_amount_examples():
    assert format_amount(Decimal("1234567.00"), "rp_dot") == "Rp 1.234.567"
    assert format_amount(Decimal("1234567.00"), "dot_comma") == "1.234.567,00"
    assert format_amount(Decimal("1234567.00"), "idr_comma") == "IDR 1,234,567"


@pytest.mark.parametrize("fmt", DATE_FORMATS)
def test_date_roundtrip(fmt):
    for d in (date(2026, 11, 5), date(2025, 8, 17), date(2026, 1, 31), date(2025, 5, 1)):
        assert parse_date(format_date(d, fmt)) == d


def test_date_examples():
    d = date(2026, 11, 5)
    assert [format_date(d, f) for f in DATE_FORMATS] == [
        "05 November 2026",
        "05/11/2026",
        "2026-11-05",
        "5 Nov 2026",
    ]


def _text(path):
    pdf = pypdfium2.PdfDocument(path)
    try:
        return pdf[0].get_textpage().get_text_range(), len(pdf)
    finally:
        pdf.close()


@pytest.mark.parametrize("index", [1, 2, 3, 4, 5, 6])
def test_rendered_pdf_contains_invoice_number(tmp_path, index):
    si = make_invoice(42, index, False)
    render_invoice_pdf(si, tmp_path / "a.pdf")
    text, pages = _text(tmp_path / "a.pdf")
    assert pages == 1
    assert si.invoice.invoice_number in text
    assert format_amount(si.invoice.total, si.layout.number_style) in text


def test_degraded_pdf_is_image_only(tmp_path):
    render_invoice_pdf(make_invoice(42, 1, False), tmp_path / "a.pdf")
    degrade_pdf(tmp_path / "a.pdf", tmp_path / "b.pdf", "scan_heavy", random.Random(1))
    text, pages = _text(tmp_path / "b.pdf")
    assert pages == 1 and text.strip() == ""
    assert render_first_page(tmp_path / "b.pdf").mode == "RGB"


def test_render_first_page_reads_images(tmp_path):
    from PIL import Image

    Image.new("L", (20, 10), 128).save(tmp_path / "x.png")
    img = render_first_page(tmp_path / "x.png")
    assert img.mode == "RGB" and img.size == (20, 10)
