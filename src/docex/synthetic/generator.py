"""Synthetic Indonesian invoices: consistent data, optional injected faults, and dataset files."""

from __future__ import annotations

import random
import zlib
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from typing import Literal

from faker import Faker

from docex.schemas import Invoice, InvoiceLineItem
from docex.synthetic.catalog import (
    DATE_FORMATS,
    INVOICE_NUMBER_FORMATS,
    NUMBER_STYLES,
    PRODUCTS,
    TEMPLATES,
)

FAULT_TYPES = (
    "total_mismatch",
    "tax_mismatch",
    "line_amount_mismatch",
    "invalid_npwp",
    "due_before_issue",
)
FAULT_RULE = {
    "total_mismatch": "R06",
    "tax_mismatch": "R05",
    "line_amount_mismatch": "R02",
    "invalid_npwp": "R07",
    "due_before_issue": "R09",
}

FIRST_DATE = date(2025, 1, 1)
LAST_DATE = date(2026, 10, 31)
CENT = Decimal("0.01")
RUPIAH = Decimal("1")


@dataclass(frozen=True)
class InvoiceLayout:
    template: str
    date_format: str
    number_style: str
    seller_address: str
    buyer_address: str


@dataclass(frozen=True)
class SyntheticInvoice:
    doc_id: str
    invoice: Invoice
    layout: InvoiceLayout
    tax_scheme: Literal["ppn11", "dpp_nilai_lain"]
    faults: tuple[str, ...]


@lru_cache(maxsize=1)
def _faker() -> Faker:
    return Faker("id_ID")


def _rupiah(value: Decimal) -> Decimal:
    return value.quantize(RUPIAH, rounding=ROUND_HALF_UP).quantize(CENT)


def _npwp(rng: random.Random) -> str:
    if rng.random() < 0.5:
        d = "".join(str(rng.randint(0, 9)) for _ in range(15))
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}.{d[8]}-{d[9:12]}.{d[12:]}"
    return "".join(str(rng.randint(0, 9)) for _ in range(16))


def _delta(rng: random.Random) -> Decimal:
    """A visible error: at least Rp 1.000, well above rounding tolerance."""
    return Decimal(rng.choice((-1, 1)) * rng.randint(2, 100) * 500)


def make_invoice(seed: int, index: int, faulty: bool) -> SyntheticInvoice:
    key = f"{seed}:inv:{index}"
    rng = random.Random(key)
    fake = _faker()
    fake.seed_instance(zlib.crc32(key.encode()))

    layout = InvoiceLayout(
        template=rng.choice(TEMPLATES),
        date_format=rng.choice(DATE_FORMATS),
        number_style=rng.choice(NUMBER_STYLES),
        seller_address=fake.address().replace("\n", ", "),
        buyer_address=fake.address().replace("\n", ", "),
    )
    seller = fake.company()
    buyer = fake.company()
    while buyer == seller:
        buyer = fake.company()

    invoice_date = FIRST_DATE + timedelta(days=rng.randint(0, (LAST_DATE - FIRST_DATE).days))
    number_format = rng.choice(INVOICE_NUMBER_FORMATS)
    invoice_number = number_format.format(
        y=invoice_date.year, m=invoice_date.month, n=rng.randint(1, 9999)
    )
    due_date = (
        None if rng.random() < 0.2 else invoice_date + timedelta(days=rng.choice((14, 30, 45)))
    )

    items = []
    for description, low, high in rng.sample(PRODUCTS, rng.randint(1, 8)):
        quantity = Decimal(rng.randint(1, 20))
        unit_price = Decimal(max(500, round(rng.randint(low, high) / 500) * 500)).quantize(CENT)
        items.append(
            InvoiceLineItem(
                description=description,
                quantity=quantity,
                unit_price=unit_price,
                amount=(quantity * unit_price).quantize(CENT),
            )
        )
    subtotal = sum((it.amount for it in items), Decimal("0")).quantize(CENT)
    discount = Decimal("0").quantize(CENT)
    if rng.random() < 0.3:
        discount = _rupiah(subtotal * rng.choice((Decimal("0.05"), Decimal("0.10"))))
    net = subtotal - discount

    tax_scheme: Literal["ppn11", "dpp_nilai_lain"]
    if rng.random() < 0.5:
        tax_scheme, tax_base, tax_rate = "ppn11", net, Decimal("0.11")
    else:
        tax_scheme, tax_base, tax_rate = "dpp_nilai_lain", _rupiah(net * 11 / 12), Decimal("0.12")
    tax_amount = _rupiah(tax_base * tax_rate)
    total = net + tax_amount

    seller_npwp = _npwp(rng)
    buyer_npwp = _npwp(rng) if rng.random() < 0.6 else None

    faults: tuple[str, ...] = ()
    if faulty:
        fault = rng.choice(FAULT_TYPES)
        faults = (fault,)
        if fault == "total_mismatch":
            total += _delta(rng)
        elif fault == "tax_mismatch":
            delta = _delta(rng)
            tax_amount += delta
            total += delta  # the total is consistent with the (wrong) printed tax
        elif fault == "line_amount_mismatch":
            i = rng.randrange(len(items))
            items[i] = items[i].model_copy(update={"amount": items[i].amount + abs(_delta(rng))})
        elif fault == "invalid_npwp":
            digits = "".join(c for c in seller_npwp if c.isdigit())
            seller_npwp = digits[:-1]  # 14 or 15 digits
            if len(seller_npwp) != 14:
                seller_npwp = seller_npwp[:-1]
        elif fault == "due_before_issue":
            due_date = invoice_date - timedelta(days=rng.randint(1, 10))

    invoice = Invoice(
        invoice_number=invoice_number,
        invoice_date=invoice_date,
        due_date=due_date,
        seller_name=seller,
        seller_npwp=seller_npwp,
        buyer_name=buyer,
        buyer_npwp=buyer_npwp,
        line_items=items,
        subtotal=subtotal,
        discount=discount,
        tax_base=tax_base.quantize(CENT),
        tax_rate=tax_rate,
        tax_amount=tax_amount,
        total=total,
    )
    return SyntheticInvoice(f"inv-{index:04d}", invoice, layout, tax_scheme, faults)
