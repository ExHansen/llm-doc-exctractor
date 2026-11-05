"""An offline extractor that returns ground truth with LLM/OCR-like mistakes.

It exists so the whole QC pipeline (validation, confidence, routing, review, evaluation) can be
built and measured without a model. Every number it produces is simulated.
"""

from __future__ import annotations

import copy
import json
import random
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from docex.groundtruth import read_ground_truth
from docex.results import ExtractionResult
from docex.schemas import FIELD_KINDS, ITEM_FIELD_KINDS, ITEMS_KEY, DocType, DocumentMeta, FieldKind

QUALITY_MULTIPLIER = {"clean": 1.0, "scan_light": 1.5, "scan_heavy": 3.0, "photo": 2.0}

_FAIL = object()  # an operator that cannot apply to this value

# ---------------------------------------------------------------- error operators


def _digit_swap(value: str, rng: random.Random) -> Any:
    spots = [
        i for i in range(len(value) - 1)
        if value[i].isdigit() and value[i + 1].isdigit() and value[i] != value[i + 1]
    ]  # fmt: skip
    if not spots:
        return _FAIL
    i = rng.choice(spots)
    return value[:i] + value[i + 1] + value[i] + value[i + 2 :]


def _drop_digit(value: str, rng: random.Random) -> Any:
    integer = value.split(".")[0]
    digits = [i for i, c in enumerate(integer) if c.isdigit()]
    if len(digits) < 2:
        digits = [i for i, c in enumerate(value) if c.isdigit()]
        if len(digits) < 2:
            return _FAIL
    i = rng.choice(digits)
    return value[:i] + value[i + 1 :]


def _thousand_sep(value: str, rng: random.Random) -> Any:
    try:
        number = Decimal(value)
    except InvalidOperation:
        return _FAIL
    if number == 0:
        return _FAIL
    return str(number / 1000)


def _day_month_swap(value: str, rng: random.Random) -> Any:
    try:
        d = date.fromisoformat(value)
    except ValueError:
        return _FAIL
    if d.day > 12 or d.day == d.month:
        return _FAIL
    return date(d.year, d.day, d.month).isoformat()


def _year_off_by_one(value: str, rng: random.Random) -> Any:
    try:
        d = date.fromisoformat(value)
        return d.replace(year=d.year + rng.choice((-1, 1))).isoformat()
    except ValueError:
        return _FAIL


def _typo(value: str, rng: random.Random) -> Any:
    spots = [i for i, c in enumerate(value) if c.isalnum()]
    if not spots:
        return _FAIL
    i = rng.choice(spots)
    pool = "0123456789" if value[i].isdigit() else "abcdefghijklmnopqrstuvwxyz"
    if value[i].isupper():
        pool = pool.upper()
    replacement = rng.choice([c for c in pool if c != value[i]])
    return value[:i] + replacement + value[i + 1 :]


def _truncate(value: str, rng: random.Random) -> Any:
    if len(value) < 2:
        return _FAIL
    return value[: max(1, round(len(value) * 0.7))]


def _null(value: str, rng: random.Random) -> Any:
    return None


OPERATORS: dict[FieldKind, tuple] = {
    "money": (_digit_swap, _thousand_sep, _drop_digit, _null),
    "quantity": (_digit_swap, _thousand_sep, _drop_digit, _null),
    "rate": (_digit_swap, _thousand_sep, _drop_digit, _null),
    "date": (_day_month_swap, _year_off_by_one, _null),
    "id": (_typo, _truncate, _null),
    "text": (_typo, _truncate, _null),
    "npwp": (_digit_swap, _drop_digit),
}


def _hallucinate(kind: FieldKind, rng: random.Random, context: dict) -> Any:
    if kind == "date":
        try:
            return (
                date.fromisoformat(context.get("invoice_date")) + timedelta(days=30)
            ).isoformat()
        except (TypeError, ValueError):
            return "2026-01-01"
    if kind == "npwp":
        return "".join(str(rng.randint(0, 9)) for _ in range(15))
    if kind == "money":
        return str(Decimal(rng.randint(1000, 100000)).quantize(Decimal("0.01")))
    if kind == "quantity":
        return str(rng.randint(1, 5))
    if kind == "rate":
        return "0.11"
    return "N/A"


def _maybe_corrupt(value: Any, kind: FieldKind, p: float, rng: random.Random, context: dict) -> Any:
    """Return a corrupted value, or _FAIL when this field stays correct."""
    if value is None:
        return _hallucinate(kind, rng, context) if rng.random() < p / 3 else _FAIL
    if rng.random() >= p:
        return _FAIL
    text = str(value)
    operators = list(OPERATORS[kind])
    rng.shuffle(operators)
    for op in operators:
        result = op(text, rng)
        if result is not _FAIL and result != text:
            return result
    return None if kind != "npwp" else _FAIL


# ---------------------------------------------------------------- corruption of a whole document


def _corrupt_fields(
    data: dict, doc_type: DocType, p: float, rng: random.Random
) -> tuple[dict, set[str]]:
    out = copy.deepcopy(data)
    paths: set[str] = set()
    for field, kind in FIELD_KINDS[doc_type].items():
        new = _maybe_corrupt(out.get(field), kind, p, rng, data)
        if new is not _FAIL:
            out[field] = new
            paths.add(field)
    key = ITEMS_KEY[doc_type]
    for i, item in enumerate(out.get(key) or []):
        for field, kind in ITEM_FIELD_KINDS[doc_type].items():
            new = _maybe_corrupt(item.get(field), kind, p, rng, data)
            if new is not _FAIL:
                item[field] = new
                paths.add(f"{key}.{i}.{field}")
    return out, paths


def _dropped_items(data: dict, doc_type: DocType, p: float, rng: random.Random) -> set[int]:
    return {i for i in range(len(data.get(ITEMS_KEY[doc_type]) or [])) if rng.random() < p}


def _remove_items(out: dict, doc_type: DocType, dropped: set[int]) -> dict:
    key = ITEMS_KEY[doc_type]
    if key in out and out[key] is not None:
        out[key] = [it for i, it in enumerate(out[key]) if i not in dropped]
    return out


def _get(data: dict, path: str) -> Any:
    node: Any = data
    for part in path.split("."):
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node


def _set(data: dict, path: str, value: Any) -> None:
    *parents, last = path.split(".")
    node: Any = data
    for part in parents:
        node = node[int(part)] if isinstance(node, list) else node[part]
    node[last] = value


def corrupt(data: dict, doc_type: DocType, p: float, rng: random.Random) -> tuple[dict, set[str]]:
    """Apply the error model once. Returns the corrupted copy and the corrupted paths."""
    out, paths = _corrupt_fields(data, doc_type, p, rng)
    dropped = _dropped_items(data, doc_type, p, rng)
    paths |= {f"{ITEMS_KEY[doc_type]}.{i}" for i in dropped}
    return _remove_items(out, doc_type, dropped), paths


# ---------------------------------------------------------------- provider


class MockProvider:
    name = "mock"
    model = "mock-v1"

    def __init__(
        self,
        data_dir: Path,
        seed: int = 42,
        base_error_rate: float = 0.03,
        consistency_correlation: float = 0.5,
        failure_rate: float = 0.01,
    ):
        self.data_dir = Path(data_dir)
        self.seed = seed
        self.base_error_rate = base_error_rate
        self.consistency_correlation = consistency_correlation
        self.failure_rate = failure_rate

    def _attempt(self, gt: dict, doc: DocumentMeta, p: float, attempt: int) -> dict:
        key = f"{self.seed}:{doc.doc_id}"
        rng1 = random.Random(f"{key}:1")
        first, first_paths = _corrupt_fields(gt, doc.doc_type, p, rng1)
        dropped = _dropped_items(gt, doc.doc_type, p, rng1)
        if attempt == 1:
            return _remove_items(first, doc.doc_type, dropped)
        later, _ = _corrupt_fields(gt, doc.doc_type, p, random.Random(f"{key}:{attempt}"))
        repeat = random.Random(f"{key}:corr:{attempt}")
        for path in sorted(first_paths):
            if repeat.random() < self.consistency_correlation:
                _set(later, path, _get(first, path))
        return _remove_items(later, doc.doc_type, dropped)

    def extract(self, doc: DocumentMeta, schema: type[BaseModel], attempt: int) -> ExtractionResult:
        fail_rng = random.Random(f"{self.seed}:{doc.doc_id}:{attempt}:fail")
        if fail_rng.random() < self.failure_rate:
            return ExtractionResult(
                "failed", None, "simulated provider failure", 50.0, None, None, 0.0, True
            )
        gt_path = self.data_dir / doc.gt_path
        if not gt_path.exists():
            return ExtractionResult(
                "failed", None, f"ground truth not found: {doc.gt_path}", 0.0, None, None, 0.0, True
            )
        gt = read_ground_truth(gt_path).data
        p = min(1.0, self.base_error_rate * QUALITY_MULTIPLIER[doc.quality])
        data = self._attempt(gt, doc, p, attempt)
        output_chars = len(json.dumps(data))
        jitter = random.Random(f"{self.seed}:{doc.doc_id}:{attempt}:latency").uniform(0, 400)
        return ExtractionResult(
            status="ok",
            data=data,
            error=None,
            latency_ms=round(900 + 2 * output_chars + jitter, 1),
            input_tokens=1500,
            output_tokens=output_chars // 4,
            cost_usd=0.0,
            simulated=True,
        )
