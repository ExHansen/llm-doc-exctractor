"""Turn raw extractor output into a draft and check it against business rules R00-R23."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from pydantic import BaseModel

from docex.results import RuleResult
from docex.schemas import (
    DRAFTS,
    FIELD_KINDS,
    ITEM_DRAFTS,
    ITEM_FIELD_KINDS,
    ITEMS_KEY,
    REQUIRED_FIELDS,
    DocType,
    FieldKind,
)
from docex.validation.normalize import (
    ParseError,
    is_valid_npwp,
    npwp_digits,
    parse_date,
    parse_number,
    parse_rate,
)

CENT = Decimal("0.01")
ONE = Decimal("1")
VALID_TAX_RATES = (Decimal("0.11"), Decimal("0.12"))
RECEIPT_R11_FIELDS = ("subtotal", "discount", "service_charge", "tax", "total", "cash", "change")


@dataclass
class ValidationOutcome:
    draft: BaseModel
    results: list[RuleResult]


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _money(value: Any) -> Decimal | None:
    number = parse_number(value)
    return None if number is None else number.quantize(CENT, rounding=ROUND_HALF_UP)


PARSERS: dict[FieldKind, Callable[[Any], Any]] = {
    "money": _money,
    "quantity": parse_number,
    "rate": parse_rate,
    "date": parse_date,
    "id": _as_str,
    "text": _as_str,
    "npwp": _as_str,
}


def _parse_fields(
    source: dict, kinds: dict[str, FieldKind], prefix: str, errors: list[RuleResult]
) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for name, kind in kinds.items():
        raw = source.get(name)
        try:
            parsed[name] = PARSERS[kind](raw)
        except (ParseError, TypeError, ValueError) as exc:
            parsed[name] = None
            path = f"{prefix}{name}"
            errors.append(RuleResult("R00_parse", "hard", False, (path,), f"{path}: {exc}"))
    return parsed


def build_draft(raw: dict | None, doc_type: DocType) -> tuple[BaseModel, list[RuleResult]]:
    """Parse every field leniently; unparseable values become None plus an R00_parse failure."""
    errors: list[RuleResult] = []
    source = raw if isinstance(raw, dict) else {}
    fields = _parse_fields(source, FIELD_KINDS[doc_type], "", errors)
    items_key = ITEMS_KEY[doc_type]
    raw_items = source.get(items_key) or []
    if not isinstance(raw_items, list):
        errors.append(
            RuleResult("R00_parse", "hard", False, (items_key,), f"{items_key}: not a list")
        )
        raw_items = []
    items = []
    for i, raw_item in enumerate(raw_items):
        prefix = f"{items_key}.{i}."
        if not isinstance(raw_item, dict):
            path = f"{items_key}.{i}"
            errors.append(RuleResult("R00_parse", "hard", False, (path,), f"{path}: not an object"))
            continue
        item_fields = _parse_fields(raw_item, ITEM_FIELD_KINDS[doc_type], prefix, errors)
        items.append(ITEM_DRAFTS[doc_type](**item_fields))
    draft = DRAFTS[doc_type](**fields, **{items_key: items})
    return draft, errors


def _close(a: Decimal, b: Decimal, tolerance: Decimal = ONE) -> bool:
    return abs(a - b) <= tolerance


def _rule(rule_id: str, severity: str, passed: bool, fields, fail_msg: str) -> RuleResult:
    message = "ok" if passed else fail_msg
    return RuleResult(rule_id, severity, passed, tuple(fields), message)  # type: ignore[arg-type]


def _required(draft: BaseModel, doc_type: DocType) -> RuleResult:
    missing = [f for f in REQUIRED_FIELDS[doc_type] if getattr(draft, f) is None]
    if doc_type == "invoice" and not draft.line_items:
        missing.append("line_items")
    return _rule("R01", "hard", not missing, missing, f"missing required: {', '.join(missing)}")


def _invoice_rules(d: BaseModel, today: date) -> list[RuleResult]:
    out: list[RuleResult] = []
    items = d.line_items
    for i, it in enumerate(items):
        if None in (it.quantity, it.unit_price, it.amount):
            continue
        paths = tuple(f"line_items.{i}.{f}" for f in ("quantity", "unit_price", "amount"))
        ok = _close(it.quantity * it.unit_price, it.amount)
        msg = f"line {i + 1}: {it.quantity} x {it.unit_price} != {it.amount}"
        out.append(_rule("R02", "hard", ok, paths, msg))

    discount = d.discount or Decimal("0")
    if d.subtotal is not None and items and all(it.amount is not None for it in items):
        total_amount = sum((it.amount for it in items), Decimal("0"))
        paths = ("subtotal", *(f"line_items.{i}.amount" for i in range(len(items))))
        ok = _close(total_amount, d.subtotal, Decimal(len(items)))
        out.append(_rule("R03", "hard", ok, paths, f"subtotal {d.subtotal} != sum {total_amount}"))

    if d.tax_base is not None and d.subtotal is not None:
        net = d.subtotal - discount
        dpp_other = (net * 11 / 12).quantize(ONE, rounding=ROUND_HALF_UP)
        ok = _close(d.tax_base, net) or _close(d.tax_base, dpp_other)
        msg = f"tax_base {d.tax_base} matches neither {net} nor 11/12 x net ({dpp_other})"
        out.append(_rule("R04", "soft", ok, ("tax_base",), msg))

    if None not in (d.tax_base, d.tax_rate, d.tax_amount):
        expected = d.tax_base * d.tax_rate
        ok = _close(expected, d.tax_amount)
        msg = f"tax_amount {d.tax_amount} != {d.tax_base} x {d.tax_rate}"
        out.append(_rule("R05", "hard", ok, ("tax_base", "tax_rate", "tax_amount"), msg))

    if None not in (d.subtotal, d.tax_amount, d.total):
        expected = d.subtotal - discount + d.tax_amount
        ok = _close(expected, d.total)
        msg = f"total {d.total} != subtotal - discount + tax ({expected})"
        out.append(_rule("R06", "hard", ok, ("subtotal", "discount", "tax_amount", "total"), msg))

    if d.seller_npwp is not None:  # a missing NPWP is reported by R01
        seller_ok = is_valid_npwp(npwp_digits(d.seller_npwp))
        msg = f"invalid seller NPWP: {d.seller_npwp!r}"
        out.append(_rule("R07", "hard", seller_ok, ("seller_npwp",), msg))
    if d.buyer_npwp is not None:
        buyer_ok = is_valid_npwp(npwp_digits(d.buyer_npwp))
        out.append(
            _rule(
                "R07B", "soft", buyer_ok, ("buyer_npwp",), f"invalid buyer NPWP: {d.buyer_npwp!r}"
            )
        )

    if d.invoice_date is not None:
        ok = 2015 <= d.invoice_date.year <= today.year + 1
        msg = f"invoice year {d.invoice_date.year} outside 2015-{today.year + 1}"
        out.append(_rule("R08", "soft", ok, ("invoice_date",), msg))

    if d.invoice_date is not None and d.due_date is not None:
        ok = d.due_date >= d.invoice_date
        msg = f"due_date {d.due_date} is before invoice_date {d.invoice_date}"
        out.append(_rule("R09", "hard", ok, ("invoice_date", "due_date"), msg))

    if d.tax_rate is not None:
        ok = d.tax_rate in VALID_TAX_RATES
        out.append(_rule("R10", "soft", ok, ("tax_rate",), f"unusual tax rate {d.tax_rate}"))

    money: dict[str, Decimal | None] = {
        f: getattr(d, f) for f, k in FIELD_KINDS["invoice"].items() if k == "money"
    }
    for i, it in enumerate(items):
        money[f"line_items.{i}.unit_price"] = it.unit_price
        money[f"line_items.{i}.amount"] = it.amount
    out.extend(_non_negative(money))
    return out


def _non_negative(values: dict[str, Decimal | None]) -> list[RuleResult]:
    present = {k: v for k, v in values.items() if v is not None}
    if not present:
        return []
    negative = [k for k, v in present.items() if v < 0]
    return [_rule("R11", "hard", not negative, negative, f"negative amount: {', '.join(negative)}")]


def _receipt_rules(d: BaseModel) -> list[RuleResult]:
    out: list[RuleResult] = []
    out.append(_rule("R20", "hard", d.total is not None, ("total",), "total is missing"))

    items = d.items
    if d.subtotal is not None and items and all(it.price is not None for it in items):
        total_price = sum((it.price for it in items), Decimal("0"))
        paths = ("subtotal", *(f"items.{i}.price" for i in range(len(items))))
        ok = _close(total_price, d.subtotal, Decimal(len(items)))
        out.append(_rule("R21", "soft", ok, paths, f"subtotal {d.subtotal} != sum {total_price}"))

    if d.subtotal is not None and d.total is not None:
        zero = Decimal("0")
        expected = d.subtotal - (d.discount or zero) + (d.service_charge or zero) + (d.tax or zero)
        ok = _close(expected, d.total)
        fields = ("subtotal", "discount", "service_charge", "tax", "total")
        out.append(_rule("R22", "soft", ok, fields, f"total {d.total} != expected {expected}"))

    if None not in (d.cash, d.change, d.total):
        ok = _close(d.cash - d.total, d.change)
        msg = f"change {d.change} != cash {d.cash} - total {d.total}"
        out.append(_rule("R23", "soft", ok, ("cash", "change", "total"), msg))

    out.extend(_non_negative({f: getattr(d, f) for f in RECEIPT_R11_FIELDS}))
    return out


def validate(raw: dict | None, doc_type: DocType, today: date) -> ValidationOutcome:
    draft, results = build_draft(raw, doc_type)
    if doc_type == "invoice":
        results.append(_required(draft, doc_type))
        results.extend(_invoice_rules(draft, today))
    else:  # receipts: R20 is the required-field rule (the receipt's only one is `total`)
        results.extend(_receipt_rules(draft))
    return ValidationOutcome(draft=draft, results=results)
