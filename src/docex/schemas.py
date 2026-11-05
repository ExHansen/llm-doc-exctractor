"""Document schemas: strict models, lenient drafts, and field metadata."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

DocType = Literal["invoice", "receipt"]
Quality = Literal["clean", "scan_light", "scan_heavy", "photo"]
FieldKind = Literal["money", "quantity", "rate", "date", "id", "npwp", "text"]


# --- Strict models: ground truth and reviewer corrections must satisfy these. ---


class InvoiceLineItem(BaseModel):
    description: str
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal


class Invoice(BaseModel):
    doc_type: Literal["invoice"] = "invoice"
    invoice_number: str
    invoice_date: date
    due_date: date | None = None
    seller_name: str
    seller_npwp: str | None = None
    buyer_name: str
    buyer_npwp: str | None = None
    currency: Literal["IDR"] = "IDR"
    line_items: list[InvoiceLineItem]
    subtotal: Decimal
    discount: Decimal = Decimal("0")
    tax_base: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    total: Decimal


class ReceiptItem(BaseModel):
    name: str
    quantity: Decimal | None = None
    price: Decimal | None = None


class Receipt(BaseModel):
    doc_type: Literal["receipt"] = "receipt"
    items: list[ReceiptItem]
    subtotal: Decimal | None = None
    discount: Decimal | None = None
    service_charge: Decimal | None = None
    tax: Decimal | None = None
    total: Decimal | None = None
    cash: Decimal | None = None
    change: Decimal | None = None


# --- Draft models: every field optional, so a partly broken extraction keeps its good fields. ---


class InvoiceLineItemDraft(BaseModel):
    description: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    amount: Decimal | None = None


class InvoiceDraft(BaseModel):
    doc_type: Literal["invoice"] = "invoice"
    invoice_number: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    seller_name: str | None = None
    seller_npwp: str | None = None
    buyer_name: str | None = None
    buyer_npwp: str | None = None
    currency: Literal["IDR"] = "IDR"
    line_items: list[InvoiceLineItemDraft] = []
    subtotal: Decimal | None = None
    discount: Decimal | None = None
    tax_base: Decimal | None = None
    tax_rate: Decimal | None = None
    tax_amount: Decimal | None = None
    total: Decimal | None = None


class ReceiptItemDraft(BaseModel):
    name: str | None = None
    quantity: Decimal | None = None
    price: Decimal | None = None


class ReceiptDraft(BaseModel):
    doc_type: Literal["receipt"] = "receipt"
    items: list[ReceiptItemDraft] = []
    subtotal: Decimal | None = None
    discount: Decimal | None = None
    service_charge: Decimal | None = None
    tax: Decimal | None = None
    total: Decimal | None = None
    cash: Decimal | None = None
    change: Decimal | None = None


SCHEMAS: dict[DocType, type[BaseModel]] = {"invoice": Invoice, "receipt": Receipt}
DRAFTS: dict[DocType, type[BaseModel]] = {"invoice": InvoiceDraft, "receipt": ReceiptDraft}
ITEM_DRAFTS: dict[DocType, type[BaseModel]] = {
    "invoice": InvoiceLineItemDraft,
    "receipt": ReceiptItemDraft,
}
ITEMS_KEY: dict[DocType, str] = {"invoice": "line_items", "receipt": "items"}

FIELD_KINDS: dict[DocType, dict[str, FieldKind]] = {
    "invoice": {
        "invoice_number": "id",
        "invoice_date": "date",
        "due_date": "date",
        "seller_name": "text",
        "seller_npwp": "npwp",
        "buyer_name": "text",
        "buyer_npwp": "npwp",
        "subtotal": "money",
        "discount": "money",
        "tax_base": "money",
        "tax_rate": "rate",
        "tax_amount": "money",
        "total": "money",
    },
    "receipt": {
        "subtotal": "money",
        "discount": "money",
        "service_charge": "money",
        "tax": "money",
        "total": "money",
        "cash": "money",
        "change": "money",
    },
}

ITEM_FIELD_KINDS: dict[DocType, dict[str, FieldKind]] = {
    "invoice": {
        "description": "text",
        "quantity": "quantity",
        "unit_price": "money",
        "amount": "money",
    },
    "receipt": {"name": "text", "quantity": "quantity", "price": "money"},
}

REQUIRED_FIELDS: dict[DocType, tuple[str, ...]] = {
    "invoice": (
        "invoice_number",
        "invoice_date",
        "seller_name",
        "buyer_name",
        "subtotal",
        "tax_base",
        "tax_rate",
        "tax_amount",
        "total",
    ),
    "receipt": ("total",),
}

CRITICAL_FIELDS: dict[DocType, tuple[str, ...]] = {
    "invoice": (
        "invoice_number",
        "invoice_date",
        "seller_name",
        "seller_npwp",
        "subtotal",
        "tax_amount",
        "total",
    ),
    "receipt": ("total", "subtotal"),
}


@dataclass(frozen=True)
class DocumentMeta:
    """A registered document. Paths are POSIX strings relative to the data directory."""

    doc_id: str
    doc_type: DocType
    source: Literal["synthetic", "cord"]
    path: str
    quality: Quality
    template: str | None
    injected_faults: tuple[str, ...]
    gt_path: str
