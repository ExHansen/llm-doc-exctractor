import io
import json
from datetime import date

import duckdb
import pytest
from PIL import Image
from typer.testing import CliRunner

from docex.cli import app
from docex.config import Settings
from docex.datasets import cord
from docex.datasets.cord import load_cord_rows, materialize_cord, normalize_cord_gt
from docex.evaluation.metrics import build_records
from docex.groundtruth import read_ground_truth
from docex.pipeline import run_pipeline
from docex.providers.registry import get_provider
from docex.schemas import ReceiptDraft
from docex.storage import Store

runner = CliRunner()


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 60), "white").save(buffer, "PNG")
    return buffer.getvalue()


@pytest.fixture
def cord_parquet(tmp_path):
    rows = [
        {
            "gt_parse": {
                "menu": [{"nm": "Nasi Goreng", "cnt": "2", "price": "60.000"}],
                "sub_total": {"subtotal_price": "60.000", "discount_price": "-5,000"},
                "total": {"total_price": "55.000", "cashprice": "100.000", "changeprice": "45.000"},
            }
        },
        {
            "gt_parse": {
                "menu": {"nm": "Es Teh", "cnt": "1", "price": "10.000"},
                "total": {"total_price": ["10.000", "10.000"]},
            }
        },
    ]
    path = tmp_path / "cord.parquet"
    con = duckdb.connect()
    con.execute("CREATE TABLE t (image STRUCT(bytes BLOB, path VARCHAR), ground_truth VARCHAR)")
    for i, gt in enumerate(rows):
        con.execute(
            "INSERT INTO t VALUES (struct_pack(bytes := ?::BLOB, path := ?), ?)",
            [_png(), f"{i}.png", json.dumps(gt)],
        )
    con.execute(f"COPY t TO '{path.as_posix()}' (FORMAT parquet)")
    con.close()
    return path


def test_normalize_cord_gt():
    data, issues = normalize_cord_gt(
        {
            "menu": {"nm": "Es Teh", "cnt": "2", "price": "10.000"},
            "total": {"total_price": ["10.000", "10.000"]},
        }
    )
    assert data["items"][0] == {"name": "Es Teh", "quantity": "2", "price": "10000.00"}
    assert data["total"] == "10000.00" and issues == ["total: multiple values"]
    ReceiptDraft.model_validate(data)


def test_unparseable_value_is_issue():
    data, issues = normalize_cord_gt({"menu": [], "total": {"total_price": "abc"}})
    assert data["total"] is None and issues == ["total: unparseable 'abc'"]


def test_discount_is_absolute():
    data, _ = normalize_cord_gt({"menu": [], "sub_total": {"discount_price": "-5,000"}})
    assert data["discount"] == "5000.00"


def test_materialize_and_run(tmp_path, cord_parquet):
    metas = materialize_cord(load_cord_rows(cord_parquet, 2), tmp_path)
    assert [m.doc_id for m in metas] == ["cord-0001", "cord-0002"]
    assert all(m.quality == "photo" and m.doc_type == "receipt" for m in metas)
    assert (tmp_path / metas[0].path).exists() and metas[0].path.endswith(".png")
    assert read_ground_truth(tmp_path / metas[1].gt_path).gt_issues == ("total: multiple values",)
    s = Settings(data_dir=tmp_path)
    with Store(s.resolved_db_path) as st:
        st.upsert_documents(metas)
        summary = run_pipeline(st, get_provider("mock", s), metas, s, date(2026, 11, 5))
        assert summary.n_docs == 2
        records = build_records(st, summary.run_id, tmp_path)
    assert len(records) == 2 and "total" not in records[1].field_correct


def test_load_respects_limit(cord_parquet):
    assert len(load_cord_rows(cord_parquet, 1)) == 1


def test_fetch_cord_offline_message(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCEX_DATA_DIR", str(tmp_path))

    def offline():
        raise OSError("offline")

    monkeypatch.setattr(cord, "download_cord_test_split", offline)
    r = runner.invoke(app, ["fetch-cord", "--n", "2"])
    assert r.exit_code == 1 and "synthetic dataset still works" in r.output


def test_fetch_cord_with_local_parquet(tmp_path, monkeypatch, cord_parquet):
    monkeypatch.setenv("DOCEX_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(cord, "download_cord_test_split", lambda: cord_parquet)
    r = runner.invoke(app, ["fetch-cord", "--n", "2"])
    assert r.exit_code == 0 and "CC-BY-4.0" in r.output
    with Store(tmp_path / "docex.duckdb") as st:
        assert len(st.list_documents(source="cord")) == 2
