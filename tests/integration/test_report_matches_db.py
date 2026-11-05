"""Spec §6: report numbers must agree with what DuckDB recorded for the run."""

import json
from datetime import date

from docex.config import Settings
from docex.evaluation.metrics import build_records, evaluate
from docex.evaluation.report import write_report
from docex.pipeline import run_pipeline
from docex.providers.registry import get_provider
from docex.storage import Store
from docex.synthetic.generator import generate_dataset


def test_report_numbers_match_database(tmp_path):
    s = Settings(data_dir=tmp_path, mock_base_error_rate=0.1)
    docs = generate_dataset(12, 42, 0.4, 0.3, tmp_path)
    with Store(s.resolved_db_path) as st:
        st.upsert_documents(docs)
        run_id = run_pipeline(st, get_provider("mock", s), docs, s, date(2026, 11, 5)).run_id
        decisions = st.get_decisions(run_id)
        records = build_records(st, run_id, tmp_path)
        simulated = st.run_simulated(run_id)
    report = write_report(evaluate(records, run_id, simulated), tmp_path / "out", 0.7)
    metrics = json.loads((report.parent / "metrics.json").read_text(encoding="utf-8"))

    routes = {d["doc_id"]: d["route"] for d in decisions}
    n_auto = sum(route == "auto_approved" for route in routes.values())
    faulty = [d.doc_id for d in docs if d.injected_faults]
    caught = sum(routes[doc_id] == "needs_review" for doc_id in faulty)

    assert metrics["n_docs"] == len(decisions) == 12
    assert metrics["simulated"] is True
    assert metrics["automation_rate"] == round(n_auto / 12, 4)
    assert faulty and metrics["fault_catch_rate"] == round(caught / len(faulty), 4)
    at_run_threshold = next(r for r in metrics["tradeoff"] if r["threshold"] == 0.7)
    assert at_run_threshold["automation_rate"] == metrics["automation_rate"]
    assert sum(g["n"] for g in metrics["breakdown"]["quality"].values()) == 12
