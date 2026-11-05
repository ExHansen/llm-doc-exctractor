"""Result types shared by providers, validation, scoring, routing, storage and the pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from docex.schemas import DocumentMeta

Severity = Literal["hard", "soft"]
Route = Literal["auto_approved", "needs_review"]


@dataclass(frozen=True)
class RuleResult:
    rule_id: str
    severity: Severity
    passed: bool
    fields: tuple[str, ...]
    message: str


@dataclass
class ExtractionResult:
    status: Literal["ok", "failed"]
    data: dict | None
    error: str | None
    latency_ms: float
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    simulated: bool


@dataclass(frozen=True)
class FieldScore:
    field: str
    value: Any
    confidence: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class Decision:
    route: Route
    doc_confidence: float
    reasons: tuple[str, ...]


@dataclass
class DocResult:
    doc: DocumentMeta
    extractions: list[ExtractionResult]
    rules: list[RuleResult]
    scores: list[FieldScore]
    decision: Decision
