"""Review-form logic, kept free of Streamlit so it can be unit-tested."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from docex.groundtruth import GroundTruth, write_ground_truth
from docex.schemas import FIELD_KINDS, ITEM_FIELD_KINDS, ITEMS_KEY, SCHEMAS, DocType
from docex.storage import Store
from docex.validation.normalize import ParseError
from docex.validation.rules import PARSERS


def _text(value: object) -> str:
    return "" if value is None else str(value)


def form_values(
    doc_type: DocType, data: dict | None
) -> tuple[dict[str, str], list[dict[str, str]]]:
    """Extraction data as strings for text inputs (never floats, so amounts stay exact)."""
    data = data or {}
    scalars = {f: _text(data.get(f)) for f in FIELD_KINDS[doc_type]}
    items = [
        {f: _text(item.get(f)) for f in ITEM_FIELD_KINDS[doc_type]}
        for item in data.get(ITEMS_KEY[doc_type]) or []
        if isinstance(item, dict)
    ]
    return scalars, items


def _parse(kinds: dict, values: dict[str, str], prefix: str, errors: list[str]) -> dict:
    parsed = {}
    for field, kind in kinds.items():
        raw = (values.get(field) or "").strip()
        try:
            parsed[field] = PARSERS[kind](raw or None)
        except (ParseError, ValueError) as exc:
            errors.append(f"{prefix}{field}: {exc}")
            parsed[field] = None
    return parsed


def build_corrected(
    doc_type: DocType, scalars: dict[str, str], items: list[dict[str, str]]
) -> tuple[dict | None, list[str]]:
    """Parse the reviewer's strings and validate them against the strict schema."""
    errors: list[str] = []
    payload = _parse(FIELD_KINDS[doc_type], scalars, "", errors)
    key = ITEMS_KEY[doc_type]
    rows = [row for row in items if any((v or "").strip() for v in row.values())]
    payload[key] = [
        _parse(ITEM_FIELD_KINDS[doc_type], row, f"{key}.{i}.", errors) for i, row in enumerate(rows)
    ]
    if doc_type == "invoice" and payload.get("discount") is None:
        payload.pop("discount")  # strict schema defaults it to 0
    try:
        model = SCHEMAS[doc_type].model_validate(payload)
    except ValidationError as exc:
        reported = {e.split(":")[0] for e in errors}
        for err in exc.errors():
            loc = ".".join(str(part) for part in err["loc"])
            if loc not in reported:
                errors.append(f"{loc}: {err['msg']}")
        return None, errors
    if errors:
        return None, errors
    return model.model_dump(mode="json"), []


def export_labels(store: Store, run_id: str, data_dir: Path) -> list[Path]:
    """Write every reviewer correction of a run as a ground-truth file under data/labels/."""
    written: list[Path] = []
    for doc_id, review in sorted(store.get_reviews(run_id).items()):
        if review["action"] != "correct":
            continue
        doc = store.get_document(doc_id)
        if doc is None:
            continue
        path = Path(data_dir) / "labels" / f"{doc_id}.json"
        write_ground_truth(
            path, GroundTruth(doc_id, doc.doc_type, doc.source, review["corrected_data"])
        )
        written.append(path)
    return written
