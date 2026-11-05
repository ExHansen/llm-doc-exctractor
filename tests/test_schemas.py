from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from docex.schemas import (
    CRITICAL_FIELDS,
    DRAFTS,
    FIELD_KINDS,
    ITEM_FIELD_KINDS,
    ITEMS_KEY,
    REQUIRED_FIELDS,
    SCHEMAS,
    DocumentMeta,
    Invoice,
    InvoiceDraft,
    Receipt,
)


def test_invoice_requires_line_items_and_totals():
    with pytest.raises(ValidationError):
        Invoice(
            invoice_number="INV/1",
            invoice_date=date(2026, 11, 5),
            seller_name="PT A",
            buyer_name="PT B",
            line_items=[],
            subtotal=Decimal("0"),
        )  # missing tax_base, tax_rate, tax_amount, total


def test_draft_accepts_partial_data():
    d = InvoiceDraft(total=Decimal("1000.00"))
    assert d.invoice_number is None and d.line_items == [] and d.doc_type == "invoice"


def test_field_kinds_cover_required_and_critical():
    for t in ("invoice", "receipt"):
        assert set(REQUIRED_FIELDS[t]) <= set(FIELD_KINDS[t])
        assert set(CRITICAL_FIELDS[t]) <= set(FIELD_KINDS[t])


def test_kind_maps_match_models():
    for t in ("invoice", "receipt"):
        model_fields = set(SCHEMAS[t].model_fields) - {"doc_type", "currency", ITEMS_KEY[t]}
        assert set(FIELD_KINDS[t]) == model_fields
        assert set(DRAFTS[t].model_fields) == set(SCHEMAS[t].model_fields)
    item_model = SCHEMAS["receipt"].model_fields["items"].annotation.__args__[0]
    assert set(ITEM_FIELD_KINDS["receipt"]) == set(item_model.model_fields)


def test_receipt_all_optional_except_items():
    r = Receipt(items=[])
    assert r.total is None and r.doc_type == "receipt"


def test_document_meta_is_frozen():
    m = DocumentMeta(
        "inv-0001",
        "invoice",
        "synthetic",
        "documents/synthetic/inv-0001.pdf",
        "clean",
        "modern",
        (),
        "ground_truth/inv-0001.json",
    )
    with pytest.raises(AttributeError):
        m.doc_id = "x"  # type: ignore[misc]
