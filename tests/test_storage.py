from datetime import datetime

from docex.results import Decision, DocResult, ExtractionResult, FieldScore, RuleResult
from docex.schemas import DocumentMeta
from docex.storage import Store

META = DocumentMeta(
    "inv-0001",
    "invoice",
    "synthetic",
    "documents/synthetic/inv-0001.pdf",
    "scan_light",
    "modern",
    ("total_mismatch",),
    "ground_truth/inv-0001.json",
)


def sample_result(doc: DocumentMeta) -> DocResult:
    ok = ExtractionResult("ok", {"total": "999.00"}, None, 1200.5, 1500, 40, 0.0, True)
    failed = ExtractionResult(
        "failed", None, "simulated provider failure", 10.0, None, None, 0.0, True
    )
    return DocResult(
        doc=doc,
        extractions=[ok, failed],
        rules=[RuleResult("R06", "hard", False, ("subtotal", "total"), "total mismatch")],
        scores=[
            FieldScore("total", "999.00", 0.5, ("R06 failed",)),
            FieldScore("seller_name", "PT A", 1.0, ()),
        ],
        decision=Decision("needs_review", 0.5, ("R06 failed: total mismatch",)),
    )


def test_documents_roundtrip(tmp_path):
    with Store(tmp_path / "d.duckdb") as s:
        s.upsert_documents([META])
        s.upsert_documents([META])
        assert s.list_documents() == [META]
        assert s.list_documents(source="cord") == []
        assert s.get_document("inv-0001") == META


def test_list_documents_limit_and_order(tmp_path):
    metas = [
        DocumentMeta(
            f"inv-000{i}",
            "invoice",
            "synthetic",
            f"documents/synthetic/inv-000{i}.pdf",
            "clean",
            "modern",
            (),
            f"ground_truth/inv-000{i}.json",
        )
        for i in (3, 1, 2)
    ]
    with Store(tmp_path / "d.duckdb") as s:
        s.upsert_documents(metas)
        assert [m.doc_id for m in s.list_documents(limit=2)] == ["inv-0001", "inv-0002"]


def test_run_ids_unique_within_same_second(tmp_path):
    now = datetime(2026, 11, 5, 9, 30, 0)
    with Store(tmp_path / "d.duckdb") as s:
        a = s.create_run("mock", "mock-v1", {}, now)
        b = s.create_run("mock", "mock-v1", {}, now)
        c = s.create_run("mock", "mock-v1", {}, now)
    assert (a, b, c) == ("20261105-093000-mock", "20261105-093000-mock-2", "20261105-093000-mock-3")


def test_run_lifecycle(tmp_path):
    with Store(tmp_path / "d.duckdb") as s:
        assert s.latest_run_id() is None
        rid = s.create_run("mock", "mock-v1", {"seed": 42})
        s.finish_run(rid, 1, "completed")
        runs = s.list_runs()
        assert s.latest_run_id() == rid
        assert (
            runs[0]["run_id"] == rid and runs[0]["status"] == "completed" and runs[0]["n_docs"] == 1
        )


def test_doc_result_roundtrip(tmp_path):
    with Store(tmp_path / "d.duckdb") as s:
        s.upsert_documents([META])
        rid = s.create_run("mock", "mock-v1", {})
        s.save_doc_result(rid, sample_result(META))
        d = s.get_doc_detail(rid, META.doc_id)
        assert d["doc"] == META
        assert d["decision"] == Decision("needs_review", 0.5, ("R06 failed: total mismatch",))
        assert d["rules"] == sample_result(META).rules
        assert d["scores"] == sample_result(META).scores
        assert [e["attempt"] for e in d["extractions"]] == [1, 2]
        assert d["extractions"][0]["data"] == {"total": "999.00"}
        assert d["extractions"][1]["error"] == "simulated provider failure"
        assert s.get_decisions(rid)[0]["reasons"] == list(d["decision"].reasons)
        assert s.run_simulated(rid) is True


def test_review_latest_wins(tmp_path):
    with Store(tmp_path / "d.duckdb") as s:
        s.save_review("r1", "inv-0001", "approve", None)
        s.save_review("r1", "inv-0001", "correct", {"total": "1.00"})
        review = s.get_reviews("r1")["inv-0001"]
        assert review["action"] == "correct" and review["corrected_data"] == {"total": "1.00"}


def test_store_releases_file_after_close(tmp_path):  # Review Focus #2
    p = tmp_path / "d.duckdb"
    with Store(p) as s:
        s.upsert_documents([META])
    with Store(p) as s2:
        assert len(s2.list_documents()) == 1
    p.unlink()  # fails on Windows if a handle is still open


def test_run_config(tmp_path):
    with Store(tmp_path / "d.duckdb") as s:
        rid = s.create_run("mock", "mock-v1", {"review_threshold": 0.6})
        assert s.get_run_config(rid) == {"review_threshold": 0.6}
        assert s.get_run_config("missing") is None


def test_latest_completed_run(tmp_path):
    with Store(tmp_path / "d.duckdb") as s:
        a = s.create_run("mock", "mock-v1", {})
        s.finish_run(a, 0, "completed")
        b = s.create_run("mock", "mock-v1", {})
        assert s.latest_run_id() == b and s.latest_run_id(status="completed") == a


def test_store_closes_connection_when_schema_fails(tmp_path, monkeypatch):
    import duckdb
    import pytest

    import docex.storage as storage

    monkeypatch.setattr(storage, "SCHEMA", "THIS IS NOT SQL")
    p = tmp_path / "d.duckdb"
    with pytest.raises(duckdb.Error):
        Store(p)
    p.unlink()  # fails on Windows if the half-built Store kept its connection
