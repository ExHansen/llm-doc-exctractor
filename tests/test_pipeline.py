from datetime import date

from docex.config import Settings
from docex.pipeline import process_document, run_pipeline
from docex.providers.registry import get_provider
from docex.storage import Store
from docex.synthetic.generator import generate_dataset

TODAY = date(2026, 11, 5)


def test_pipeline_end_to_end(tmp_path):
    s = Settings(data_dir=tmp_path, mock_base_error_rate=0.2)
    docs = generate_dataset(10, 42, 0.3, 0.3, tmp_path)
    with Store(s.resolved_db_path) as st:
        st.upsert_documents(docs)
        summary = run_pipeline(st, get_provider("mock", s), docs, s, TODAY)
        assert summary.n_docs == 10 and summary.n_auto + summary.n_review == 10
        assert summary.simulated and len(st.get_decisions(summary.run_id)) == 10
        detail = st.get_doc_detail(summary.run_id, docs[0].doc_id)
        assert len(detail["extractions"]) == s.consistency_runs
        assert st.list_runs()[0]["status"] == "completed"


def test_perfect_extractor_routes_exactly_the_faulty_docs(tmp_path):
    s = Settings(data_dir=tmp_path, mock_base_error_rate=0.0, mock_failure_rate=0.0)
    docs = generate_dataset(20, 42, 0.3, 0.3, tmp_path)
    with Store(s.resolved_db_path) as st:
        st.upsert_documents(docs)
        rid = run_pipeline(st, get_provider("mock", s), docs, s, TODAY).run_id
        routes = {d["doc_id"]: d["route"] for d in st.get_decisions(rid)}
    assert any(d.injected_faults for d in docs)
    assert routes == {
        d.doc_id: ("needs_review" if d.injected_faults else "auto_approved") for d in docs
    }


class ExplodingProvider:
    name = "mock"
    model = "mock-v1"

    def __init__(self, inner, bad_doc_id):
        self.inner, self.bad_doc_id = inner, bad_doc_id

    def extract(self, doc, schema, attempt):
        if doc.doc_id == self.bad_doc_id:
            raise RuntimeError("boom")
        return self.inner.extract(doc, schema, attempt)


def test_exception_in_one_doc_does_not_stop_run(tmp_path):
    s = Settings(data_dir=tmp_path, mock_base_error_rate=0.0, mock_failure_rate=0.0)
    docs = generate_dataset(3, 42, 0.0, 0.0, tmp_path)
    provider = ExplodingProvider(get_provider("mock", s), docs[1].doc_id)
    with Store(s.resolved_db_path) as st:
        st.upsert_documents(docs)
        summary = run_pipeline(st, provider, docs, s, TODAY)
        decisions = {d["doc_id"]: d for d in st.get_decisions(summary.run_id)}
    assert summary.n_docs == 3 and summary.n_failed == 1
    bad = decisions[docs[1].doc_id]
    assert bad["route"] == "needs_review" and bad["reasons"] == [
        "extraction failed: RuntimeError: boom"
    ]
    assert decisions[docs[0].doc_id]["route"] == "auto_approved"


def test_failed_first_attempt_routes_to_review(tmp_path):
    s = Settings(data_dir=tmp_path, mock_failure_rate=1.0)
    docs = generate_dataset(1, 42, 0.0, 0.0, tmp_path)
    result = process_document(docs[0], get_provider("mock", s), s, TODAY)
    assert result.decision.route == "needs_review" and result.rules == [] and result.scores == []
    assert result.decision.reasons == ("extraction failed: simulated provider failure",)
