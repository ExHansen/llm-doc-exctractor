"""Decide whether a document can be auto-approved or needs a human reviewer."""

from __future__ import annotations

from docex.results import Decision, FieldScore, RuleResult
from docex.schemas import DocType
from docex.scoring import critical_fields


def route(
    failed_extraction: str | None,
    rules: list[RuleResult],
    scores: list[FieldScore],
    doc_conf: float,
    threshold: float,
    doc_type: DocType,
) -> Decision:
    reasons: list[str] = []
    review = False
    if failed_extraction is not None:
        reasons.append(f"extraction failed: {failed_extraction}")
        review = True
    for rule in rules:
        if not rule.passed and rule.severity == "hard":
            reasons.append(f"{rule.rule_id} failed: {rule.message}")
            review = True
    for score in critical_fields(doc_type, scores):
        if score.confidence < threshold:
            reasons.append(f"low confidence: {score.field}={score.confidence:.2f}")
    if doc_conf < threshold:
        review = True
    return Decision("needs_review" if review else "auto_approved", doc_conf, tuple(reasons))
