"""Run extract -> validate -> score -> route for each document and persist the results."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from docex.config import Settings
from docex.providers.base import ExtractionProvider
from docex.results import DocResult, ExtractionResult
from docex.routing import route
from docex.schemas import SCHEMAS, DocumentMeta
from docex.scoring import doc_confidence, score_fields
from docex.storage import Store
from docex.validation.rules import validate


@dataclass
class RunSummary:
    run_id: str
    n_docs: int
    n_auto: int
    n_review: int
    n_failed: int
    simulated: bool


def _failed(doc: DocumentMeta, extractions: list[ExtractionResult], error: str, s: Settings):
    decision = route(error, [], [], 0.0, s.review_threshold, doc.doc_type)
    return DocResult(doc, extractions, [], [], decision)


def process_document(
    doc: DocumentMeta, provider: ExtractionProvider, settings: Settings, today: date
) -> DocResult:
    """Never raises: any problem becomes a failed extraction routed to review."""
    try:
        schema = SCHEMAS[doc.doc_type]
        runs = max(1, settings.consistency_runs)
        extractions = [provider.extract(doc, schema, attempt) for attempt in range(1, runs + 1)]
        first = extractions[0]
        if first.status != "ok":
            return _failed(doc, extractions, first.error or "unknown error", settings)
        primary = validate(first.data, doc.doc_type, today)
        others = [
            validate(e.data, doc.doc_type, today).draft for e in extractions[1:] if e.status == "ok"
        ]
        scores = score_fields(doc.doc_type, primary, others)
        confidence = doc_confidence(doc.doc_type, scores)
        decision = route(
            None, primary.results, scores, confidence, settings.review_threshold, doc.doc_type
        )
        return DocResult(doc, extractions, primary.results, scores, decision)
    except Exception as exc:  # noqa: BLE001 - one bad document must not stop the run
        error = f"{type(exc).__name__}: {exc}"
        simulated = getattr(provider, "name", "") == "mock"
        failed = ExtractionResult("failed", None, error, 0.0, None, None, None, simulated)
        return _failed(doc, [failed], error, settings)


def run_pipeline(
    store: Store,
    provider: ExtractionProvider,
    docs: list[DocumentMeta],
    settings: Settings,
    today: date | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> RunSummary:
    today = today or date.today()
    config = settings.model_dump(mode="json")
    run_id = store.create_run(provider.name, provider.model, config)
    n_auto = n_review = n_failed = 0
    simulated = False
    for i, doc in enumerate(docs, start=1):
        result = process_document(doc, provider, settings, today)
        store.save_doc_result(run_id, result)
        simulated = simulated or any(e.simulated for e in result.extractions)
        if result.extractions[0].status != "ok":
            n_failed += 1
        if result.decision.route == "auto_approved":
            n_auto += 1
        else:
            n_review += 1
        if on_progress:
            on_progress(i, len(docs))
    store.finish_run(run_id, len(docs), "completed")
    return RunSummary(run_id, len(docs), n_auto, n_review, n_failed, simulated)
