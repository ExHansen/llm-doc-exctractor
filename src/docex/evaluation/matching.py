"""Compare predicted values with ground truth the way a reviewer would."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from rapidfuzz import fuzz

from docex.schemas import ITEM_FIELD_KINDS, DocType, FieldKind
from docex.validation.normalize import (
    ParseError,
    normalize_text,
    npwp_digits,
    parse_date,
    parse_number,
    parse_rate,
)

TEXT_MATCH = 90
ITEM_PAIRING = 60
ITEM_NAME = {"invoice": "description", "receipt": "name"}


def field_match(kind: FieldKind, pred: Any, gt: Any) -> bool:
    if pred is None and gt is None:
        return True
    if pred is None or gt is None:
        return False
    try:
        if kind in ("money", "quantity"):
            p, g = parse_number(pred), parse_number(gt)
            return p is not None and g is not None and abs(p - g) <= 1
        if kind == "rate":
            p, g = parse_rate(pred), parse_rate(gt)
            return p is not None and g is not None and abs(p - g) <= Decimal("0.001")
        if kind == "date":
            return parse_date(pred) == parse_date(gt)
        if kind == "npwp":
            return npwp_digits(str(pred)) == npwp_digits(str(gt))
        if kind == "id":
            return normalize_text(str(pred)) == normalize_text(str(gt))
        return fuzz.ratio(normalize_text(str(pred)), normalize_text(str(gt))) >= TEXT_MATCH
    except (ParseError, TypeError, ValueError):
        return False


def match_items(doc_type: DocType, pred: list[dict], gt: list[dict]) -> tuple[int, int, int]:
    """Greedy name-based pairing; a pair is a true positive only if every field matches."""
    name = ITEM_NAME[doc_type]
    kinds = ITEM_FIELD_KINDS[doc_type]
    used: set[int] = set()
    tp = 0
    for g in gt:
        best, best_ratio = None, -1.0
        for j, p in enumerate(pred):
            if j in used:
                continue
            ratio = fuzz.ratio(normalize_text(p.get(name)), normalize_text(g.get(name)))
            if ratio >= ITEM_PAIRING and ratio > best_ratio:
                best, best_ratio = j, ratio
        if best is None:
            continue
        used.add(best)
        if all(field_match(k, pred[best].get(f), g.get(f)) for f, k in kinds.items()):
            tp += 1
    return tp, len(pred) - tp, len(gt) - tp
