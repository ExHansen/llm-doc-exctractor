"""Shared test fixtures-as-functions."""

from datetime import date

TODAY = date(2026, 11, 5)


def clean_invoice_raw() -> dict:
    """A consistent invoice as an extractor would return it (JSON-native values)."""
    return {
        "doc_type": "invoice",
        "invoice_number": "INV/2026/11/00123",
        "invoice_date": "2026-11-05",
        "due_date": "2026-12-05",
        "seller_name": "PT Maju Jaya Tbk",
        "seller_npwp": "01.234.567.8-901.000",
        "buyer_name": "CV Sinar Abadi",
        "buyer_npwp": None,
        "currency": "IDR",
        "line_items": [
            {
                "description": "Kertas HVS A4 80gsm (rim)",
                "quantity": "3",
                "unit_price": "15000.00",
                "amount": "45000.00",
            },
            {
                "description": "Jasa pengiriman Jakarta-Bandung",
                "quantity": "1",
                "unit_price": "55000.00",
                "amount": "55000.00",
            },
        ],
        "subtotal": "100000.00",
        "discount": "0.00",
        "tax_base": "100000.00",
        "tax_rate": "0.11",
        "tax_amount": "11000.00",
        "total": "111000.00",
    }
