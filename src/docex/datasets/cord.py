"""Real-world receipts from CORD v2 (Park et al., 2019, CC-BY-4.0), normalized to `Receipt`."""

from __future__ import annotations

import io
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb
from PIL import Image

from docex.groundtruth import GroundTruth, write_ground_truth
from docex.schemas import DocumentMeta
from docex.validation.normalize import ParseError, parse_number

CORD_REPO = "naver-clova-ix/cord-v2"
CORD_ATTRIBUTION = (
    "CORD v2 receipts (Park et al., 2019), CC-BY-4.0: https://huggingface.co/datasets/" + CORD_REPO
)
CENT = Decimal("0.01")

SUB_TOTAL_MAP = {
    "subtotal_price": "subtotal",
    "discount_price": "discount",
    "service_price": "service_charge",
    "tax_price": "tax",
}
TOTAL_MAP = {"total_price": "total", "cashprice": "cash", "changeprice": "change"}


def _single(raw: Any, field: str, issues: list[str]) -> Any:
    if isinstance(raw, list):
        issues.append(f"{field}: multiple values")
        return raw[0] if raw else None
    return raw


def _number(raw: Any, field: str, issues: list[str], money: bool) -> str | None:
    raw = _single(raw, field, issues)
    if raw is None:
        return None
    try:
        number = parse_number(raw)
    except ParseError:
        issues.append(f"{field}: unparseable '{raw}'")
        return None
    if number is None:
        return None
    return str(number.quantize(CENT)) if money else str(number)


def _as_dict(raw: Any) -> dict:
    if isinstance(raw, list):
        raw = raw[0] if raw else {}
    return raw if isinstance(raw, dict) else {}


def normalize_cord_gt(gt_parse: dict) -> tuple[dict, list[str]]:
    """Map CORD's `menu` / `sub_total` / `total` labels onto the Receipt schema."""
    issues: list[str] = []
    menu = gt_parse.get("menu") or []
    if isinstance(menu, dict):
        menu = [menu]
    items = []
    for i, entry in enumerate(m for m in menu if isinstance(m, dict)):
        name = _single(entry.get("nm"), f"items.{i}.name", issues)
        items.append({
            "name": None if name is None else str(name).strip(),
            "quantity": _number(entry.get("cnt"), f"items.{i}.quantity", issues, money=False),
            "price": _number(entry.get("price"), f"items.{i}.price", issues, money=True),
        })  # fmt: skip
    data: dict[str, Any] = {"doc_type": "receipt", "items": items}
    for source, mapping in ((gt_parse.get("sub_total"), SUB_TOTAL_MAP),
                            (gt_parse.get("total"), TOTAL_MAP)):  # fmt: skip
        section = _as_dict(source)
        for cord_key, field in mapping.items():
            data[field] = _number(section.get(cord_key), field, issues, money=True)
    if data["discount"] is not None:
        data["discount"] = str(abs(Decimal(data["discount"])))
    return data, issues


def download_cord_test_split() -> Path:
    from huggingface_hub import hf_hub_download, list_repo_files

    files = list_repo_files(CORD_REPO, repo_type="dataset")
    test_files = sorted(f for f in files if f.startswith("data/test-") and f.endswith(".parquet"))
    if not test_files:
        raise RuntimeError(f"no test split parquet found in {CORD_REPO}")
    return Path(hf_hub_download(CORD_REPO, test_files[0], repo_type="dataset"))


def load_cord_rows(parquet: Path, n: int) -> list[tuple[bytes, dict]]:
    con = duckdb.connect()
    try:
        rows = con.execute(
            "SELECT image.bytes, ground_truth FROM read_parquet(?) LIMIT ?",
            [Path(parquet).as_posix(), n],
        ).fetchall()
    finally:
        con.close()
    return [(bytes(img), json.loads(gt)["gt_parse"]) for img, gt in rows]


def materialize_cord(rows: list[tuple[bytes, dict]], data_dir: Path) -> list[DocumentMeta]:
    metas: list[DocumentMeta] = []
    for i, (image_bytes, gt_parse) in enumerate(rows, start=1):
        doc_id = f"cord-{i:04d}"
        doc_rel = f"documents/cord/{doc_id}.png"
        gt_rel = f"ground_truth/{doc_id}.json"
        target = Path(data_dir) / doc_rel
        target.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(io.BytesIO(image_bytes)) as image:
            image.convert("RGB").save(target, "PNG")
        data, issues = normalize_cord_gt(gt_parse)
        write_ground_truth(
            Path(data_dir) / gt_rel,
            GroundTruth(doc_id, "receipt", "cord", data, (), tuple(issues)),
        )
        metas.append(DocumentMeta(doc_id, "receipt", "cord", doc_rel, "photo", None, (), gt_rel))
    return metas
