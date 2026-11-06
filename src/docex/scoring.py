"""Field-level and document-level confidence from rule results and attempt agreement."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from docex.results import FieldScore
from docex.schemas import CRITICAL_FIELDS, FIELD_KINDS, ITEM_FIELD_KINDS, ITEMS_KEY, DocType
from docex.validation.rules import ValidationOutcome

FORMAT_RULES = frozenset({"R00_parse", "R07", "R07B"})
MISSING_RULES = frozenset({"R01", "R20"})
FORMAT_PENALTY = 0.3
HARD_PENALTY = 0.5
SOFT_PENALTY = 0.8
DISAGREE_PENALTY = 0.4


def _field_paths(doc_type: DocType, dumped: dict) -> list[str]:
    paths = list(FIELD_KINDS[doc_type])
    key = ITEMS_KEY[doc_type]
    for i in range(len(dumped.get(key) or [])):
        paths += [f"{key}.{i}.{f}" for f in ITEM_FIELD_KINDS[doc_type]]
    return paths


def _value(dumped: dict, path: str) -> Any:
    node: Any = dumped
    for part in path.split("."):
        if isinstance(node, list):
            index = int(part)
            if index >= len(node):
                return None
            node = node[index]
        elif isinstance(node, dict):
            node = node.get(part)
        else:
            return None
    return node


def score_fields(
    doc_type: DocType, primary: ValidationOutcome, other_drafts: list[BaseModel]
) -> list[FieldScore]:
    dumped = primary.draft.model_dump(mode="json")
    # Compare attempts on parsed values, so `3` and `3.0` agree.
    native = primary.draft.model_dump()
    others = [d.model_dump() for d in other_drafts]
    penalties: dict[str, list[tuple[float, str]]] = {}
    for rule in primary.results:
        if rule.passed:
            continue
        for field in rule.fields:
            if rule.rule_id in MISSING_RULES:
                entry = (0.0, "missing required")
            elif rule.rule_id in FORMAT_RULES:
                entry = (FORMAT_PENALTY, f"invalid format ({rule.rule_id})")
            elif rule.severity == "hard":
                entry = (HARD_PENALTY, f"{rule.rule_id} failed")
            else:
                entry = (SOFT_PENALTY, f"{rule.rule_id} failed (soft)")
            penalties.setdefault(field, []).append(entry)

    scores: list[FieldScore] = []
    for path in _field_paths(doc_type, dumped):
        value = _value(dumped, path)
        confidence = 1.0
        reasons: list[str] = []
        for factor, reason in penalties.get(path, []):
            confidence *= factor
            reasons.append(reason)
        if any(_value(other, path) != _value(native, path) for other in others):
            confidence *= DISAGREE_PENALTY
            reasons.append("attempts disagree")
        scores.append(FieldScore(path, value, round(confidence, 4), tuple(reasons)))
    return scores


def critical_fields(doc_type: DocType, scores: list[FieldScore]) -> list[FieldScore]:
    """Critical fields that count for routing. Receipt subtotal counts only when extracted."""
    critical = set(CRITICAL_FIELDS[doc_type])
    return [
        s for s in scores
        if s.field in critical
        and not (doc_type == "receipt" and s.field == "subtotal" and s.value is None)
    ]  # fmt: skip


def doc_confidence(doc_type: DocType, scores: list[FieldScore]) -> float:
    relevant = critical_fields(doc_type, scores)
    return min((s.confidence for s in relevant), default=0.0)
