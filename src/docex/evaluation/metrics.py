"""Per-document records and run-level metrics: accuracy, routing quality, calibration."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from docex.evaluation.matching import field_match, match_items
from docex.groundtruth import read_ground_truth
from docex.schemas import CRITICAL_FIELDS, FIELD_KINDS, ITEMS_KEY
from docex.storage import Store

THRESHOLDS = [round(0.05 * k, 2) for k in range(1, 20)]


@dataclass
class DocRecord:
    doc_id: str
    doc_type: str
    source: str
    quality: str
    template: str | None
    faults: tuple[str, ...]
    route: str
    doc_confidence: float
    failed: bool
    hard_failed: bool
    field_correct: dict[str, bool]
    critical_correct: bool
    field_conf: dict[str, float]
    items_tp: int
    items_fp: int
    items_fn: int


@dataclass
class EvalResult:
    run_id: str
    simulated: bool
    n_docs: int
    field_accuracy: dict[str, float]
    doc_accuracy: float | None
    item_precision: float | None
    item_recall: float | None
    item_f1: float | None
    automation_rate: float | None
    auto_approved_accuracy: float | None
    error_catch_rate: float | None
    fault_catch_rate: float | None
    fault_catch_by_type: dict[str, float]
    breakdown: dict[str, dict[str, dict[str, float]]]
    tradeoff: list[dict] = field(default_factory=list)
    calibration: list[dict] = field(default_factory=list)


def build_records(store: Store, run_id: str, data_dir: Path) -> list[DocRecord]:
    records: list[DocRecord] = []
    for decision in store.get_decisions(run_id):
        detail = store.get_doc_detail(run_id, decision["doc_id"])
        doc = detail["doc"]
        gt = read_ground_truth(Path(data_dir) / doc.gt_path)
        excluded = {issue.split(":")[0] for issue in gt.gt_issues}
        first = detail["extractions"][0]
        failed = first["status"] != "ok"
        pred = first["data"] or {}
        kinds = FIELD_KINDS[doc.doc_type]
        field_correct = {
            f: field_match(kind, pred.get(f), gt.data.get(f))
            for f, kind in kinds.items()
            if f in gt.data and f not in excluded
        }
        critical = [f for f in CRITICAL_FIELDS[doc.doc_type] if f in field_correct]
        key = ITEMS_KEY[doc.doc_type]
        tp, fp, fn = match_items(doc.doc_type, pred.get(key) or [], gt.data.get(key) or [])
        records.append(
            DocRecord(
                doc_id=doc.doc_id,
                doc_type=doc.doc_type,
                source=doc.source,
                quality=doc.quality,
                template=doc.template,
                faults=doc.injected_faults,
                route=decision["route"],
                doc_confidence=decision["doc_confidence"],
                failed=failed,
                hard_failed=any(not r.passed and r.severity == "hard" for r in detail["rules"]),
                field_correct=field_correct,
                critical_correct=not failed and all(field_correct[f] for f in critical),
                field_conf={s.field: s.confidence for s in detail["scores"] if s.field in kinds},
                items_tp=tp,
                items_fp=fp,
                items_fn=fn,
            )
        )
    return records


def _rate(hits: int, total: int) -> float | None:
    return None if total == 0 else round(hits / total, 4)


def _share(flags: list[bool]) -> float | None:
    return _rate(sum(flags), len(flags))


def _headline(records: list[DocRecord]) -> dict[str, float | None]:
    """The headline metrics, for a whole run or for one breakdown group."""
    tp = sum(r.items_tp for r in records)
    fp = sum(r.items_fp for r in records)
    fn = sum(r.items_fn for r in records)
    precision, recall = _rate(tp, tp + fp), _rate(tp, tp + fn)
    f1 = None
    if precision is not None and recall is not None:
        f1 = (
            0.0
            if precision + recall == 0
            else round(2 * precision * recall / (precision + recall), 4)
        )
    auto = [r for r in records if r.route == "auto_approved"]
    # Failed extractions always go to review, so they would only inflate the catch rate.
    wrong = [r for r in records if not r.critical_correct and not r.failed]
    faulty = [r for r in records if r.faults]
    return {
        "automation_rate": _share([r.route == "auto_approved" for r in records]),
        "auto_approved_accuracy": _share([r.critical_correct for r in auto]),
        "error_catch_rate": _share([r.route == "needs_review" for r in wrong]),
        "fault_catch_rate": _share([r.route == "needs_review" for r in faulty]),
        "doc_accuracy": _share([r.critical_correct for r in records]),
        "item_precision": precision,
        "item_recall": recall,
        "item_f1": f1,
    }


BREAKDOWN_METRICS = (
    "automation_rate",
    "auto_approved_accuracy",
    "error_catch_rate",
    "fault_catch_rate",
    "doc_accuracy",
    "item_f1",
)


def evaluate(records: list[DocRecord], run_id: str, simulated: bool) -> EvalResult:
    n = len(records)
    per_field: dict[str, list[bool]] = defaultdict(list)
    for r in records:
        for f, ok in r.field_correct.items():
            per_field[f"{r.doc_type}.{f}"].append(ok)

    headline = _headline(records)
    by_fault: dict[str, list[bool]] = defaultdict(list)
    for r in records:
        for fault in r.faults:
            by_fault[fault].append(r.route == "needs_review")

    breakdown: dict[str, dict[str, dict[str, float]]] = {}
    for key in ("quality", "source", "template"):
        groups: dict[str, list[DocRecord]] = defaultdict(list)
        for r in records:
            groups[getattr(r, key) or "n/a"].append(r)
        breakdown[key] = {}
        for name, group in sorted(groups.items()):
            metrics = _headline(group)
            breakdown[key][name] = {"n": len(group)} | {m: metrics[m] for m in BREAKDOWN_METRICS}

    tradeoff = []
    for t in THRESHOLDS:
        passed = [
            r for r in records if not r.failed and not r.hard_failed and r.doc_confidence >= t
        ]
        tradeoff.append({
            "threshold": t,
            "automation_rate": _rate(len(passed), n),
            "auto_approved_accuracy": _share([r.critical_correct for r in passed]),
        })  # fmt: skip

    bins: dict[int, list[tuple[float, bool]]] = defaultdict(list)
    critical_names = set(CRITICAL_FIELDS["invoice"]) | set(CRITICAL_FIELDS["receipt"])
    for r in records:
        for f in sorted(critical_names):
            if f in r.field_conf and f in r.field_correct:
                conf = r.field_conf[f]
                bins[min(int(conf * 10), 9)].append((conf, r.field_correct[f]))
    calibration = [
        {
            "bin_low": round(i / 10, 1),
            "bin_high": round((i + 1) / 10, 1),
            "n": len(points),
            "mean_confidence": round(sum(c for c, _ in points) / len(points), 4),
            "accuracy": _share([ok for _, ok in points]),
        }
        for i, points in sorted(bins.items())
    ]

    return EvalResult(
        run_id=run_id,
        simulated=simulated,
        n_docs=n,
        field_accuracy={f: _share(v) for f, v in sorted(per_field.items())},
        doc_accuracy=headline["doc_accuracy"],
        item_precision=headline["item_precision"],
        item_recall=headline["item_recall"],
        item_f1=headline["item_f1"],
        automation_rate=headline["automation_rate"],
        auto_approved_accuracy=headline["auto_approved_accuracy"],
        error_catch_rate=headline["error_catch_rate"],
        fault_catch_rate=headline["fault_catch_rate"],
        fault_catch_by_type={k: _share(v) for k, v in sorted(by_fault.items())},
        breakdown=breakdown,
        tradeoff=tradeoff,
        calibration=calibration,
    )
