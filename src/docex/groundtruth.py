"""Ground-truth files: the values printed on each document, plus known faults and issues."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from docex.schemas import DocType


@dataclass(frozen=True)
class GroundTruth:
    doc_id: str
    doc_type: DocType
    source: str
    data: dict
    injected_faults: tuple[str, ...] = ()
    gt_issues: tuple[str, ...] = ()


def write_ground_truth(path: Path, gt: GroundTruth) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "doc_id": gt.doc_id,
        "doc_type": gt.doc_type,
        "source": gt.source,
        "data": gt.data,
        "injected_faults": list(gt.injected_faults),
        "gt_issues": list(gt.gt_issues),
    }
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def read_ground_truth(path: Path) -> GroundTruth:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return GroundTruth(
        doc_id=payload["doc_id"],
        doc_type=payload["doc_type"],
        source=payload["source"],
        data=payload["data"],
        injected_faults=tuple(payload.get("injected_faults", ())),
        gt_issues=tuple(payload.get("gt_issues", ())),
    )
