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


def _latest_run(tmp_path):
    from docex.storage import Store

    with Store(tmp_path / "docex.duckdb") as st:
        return st.latest_run_id(), st


def test_review_app_approve_advances_and_saves(tmp_path):
    runner.invoke(app, ["generate", "--n", "3", "--faulty-rate", "1"])
    runner.invoke(app, ["run"])
    run_id, _ = _latest_run(tmp_path)
    key = f"doc_radio:{run_id}:needs_review"
    at = AppTest.from_file(str(REVIEW_APP), default_timeout=60).run()
    first = at.session_state[key]
    next(b for b in at.button if b.label == "Approve").click().run()
    assert not at.exception and at.session_state[key] == first + 1
    from docex.storage import Store

    with Store(tmp_path / "docex.duckdb") as st:
        assert len(st.get_reviews(run_id)) == 1


def test_review_app_discards_edits_after_approve(tmp_path):
    runner.invoke(app, ["generate", "--n", "3", "--faulty-rate", "1"])
    runner.invoke(app, ["run"])
    run_id, _ = _latest_run(tmp_path)
    at = AppTest.from_file(str(REVIEW_APP), default_timeout=60).run()
    total = next(t for t in at.text_input if t.label.startswith("total"))
    total.input("999").run()
    edited_key = total.key
    next(b for b in at.button if b.label == "Approve").click().run()
    assert not at.exception and edited_key not in at.session_state


def test_review_app_filter_change_starts_at_first_document(tmp_path):
    runner.invoke(app, ["generate", "--n", "3", "--faulty-rate", "1"])
    runner.invoke(app, ["run"])
    run_id, _ = _latest_run(tmp_path)
    at = AppTest.from_file(str(REVIEW_APP), default_timeout=60).run()
    next(b for b in at.button if b.label == "Approve").click().run()
    show = next(r for r in at.radio if r.label == "Show")
    show.set_value("all").run()
    assert not at.exception and at.session_state[f"doc_radio:{run_id}:all"] == 0


def test_review_app_reports_busy_database(tmp_path):
    import subprocess
    import sys

    runner.invoke(app, ["generate", "--n", "1"])
    runner.invoke(app, ["run"])
    holder = subprocess.Popen(
        [sys.executable, "-c",
         "import duckdb, sys, time; c = duckdb.connect(sys.argv[1]); "
         "print('locked', flush=True); time.sleep(120)",
         str(tmp_path / "docex.duckdb")],
        stdout=subprocess.PIPE, text=True,
    )  # fmt: skip
    try:
        assert holder.stdout.readline().strip() == "locked"
        at = AppTest.from_file(str(REVIEW_APP), default_timeout=60).run()
        assert not at.exception
        assert "busy" in at.error[0].value
    finally:
        holder.kill()
        holder.wait()
