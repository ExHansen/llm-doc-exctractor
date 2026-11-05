import pytest
from streamlit.testing.v1 import AppTest
from typer.testing import CliRunner

from docex.cli import REVIEW_APP, app

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCEX_DATA_DIR", str(tmp_path))
    monkeypatch.chdir(tmp_path)


def test_review_app_without_runs():
    at = AppTest.from_file(str(REVIEW_APP), default_timeout=60).run()
    assert not at.exception and "No runs yet" in at.info[0].value


def test_review_app_smoke():
    runner.invoke(app, ["generate", "--n", "3", "--faulty-rate", "1"])
    runner.invoke(app, ["run"])
    at = AppTest.from_file(str(REVIEW_APP), default_timeout=60).run()
    assert not at.exception
    labels = [b.label for b in at.button]
    assert "Approve" in labels and "Save corrections" in labels
    assert any(t.label.startswith("total") for t in at.text_input)


def test_review_app_approve_advances_and_saves(tmp_path):
    runner.invoke(app, ["generate", "--n", "3", "--faulty-rate", "1"])
    runner.invoke(app, ["run"])
    at = AppTest.from_file(str(REVIEW_APP), default_timeout=60).run()
    first = at.session_state["doc_radio"]
    next(b for b in at.button if b.label == "Approve").click().run()
    assert not at.exception and at.session_state["doc_radio"] == first + 1
    from docex.storage import Store

    with Store(tmp_path / "docex.duckdb") as st:
        assert len(st.get_reviews(st.latest_run_id())) == 1
