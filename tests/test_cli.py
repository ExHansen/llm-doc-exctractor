import pytest
from typer.testing import CliRunner

from docex.cli import app
from docex.storage import Store

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCEX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DOCEX_REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.chdir(tmp_path)


def test_generate_twice_is_idempotent(tmp_path):  # Review Focus #1
    assert runner.invoke(app, ["generate", "--n", "5"]).exit_code == 0
    assert runner.invoke(app, ["generate", "--n", "5"]).exit_code == 0
    with Store(tmp_path / "docex.duckdb") as st:
        assert len(st.list_documents()) == 5


def test_run_without_documents_exits_1():  # Review Focus #4
    r = runner.invoke(app, ["run"])
    assert r.exit_code == 1 and "docex generate" in r.output


def test_run_prints_run_id_and_simulated_notice():
    runner.invoke(app, ["generate", "--n", "4"])
    r = runner.invoke(app, ["run"])
    assert r.exit_code == 0, r.output
    assert "-mock" in r.output and "simulated extractor" in r.output


def test_run_unknown_provider_exits_2():
    runner.invoke(app, ["generate", "--n", "2"])
    r = runner.invoke(app, ["run", "--provider", "nope"])
    assert r.exit_code == 2 and "Available: mock" in r.output


def test_eval_without_runs_exits_1():  # Review Focus #4
    r = runner.invoke(app, ["eval"])
    assert r.exit_code == 1 and "docex run" in r.output


def test_eval_unknown_run_exits_1():
    runner.invoke(app, ["generate", "--n", "2"])
    runner.invoke(app, ["run"])
    r = runner.invoke(app, ["eval", "--run", "nope"])
    assert r.exit_code == 1 and "nope" in r.output


def test_eval_latest_run_writes_report(tmp_path):
    runner.invoke(app, ["generate", "--n", "4"])
    runner.invoke(app, ["run"])
    r = runner.invoke(app, ["eval"])
    assert r.exit_code == 0, r.output
    reports = list((tmp_path / "reports").glob("*/report.md"))
    assert len(reports) == 1 and "Automation rate" in r.output


def test_demo_end_to_end(tmp_path):
    r = runner.invoke(app, ["demo", "--n", "8"])
    assert r.exit_code == 0, r.output
    assert list((tmp_path / "reports").glob("*/report.md"))
    assert "simulated extractor" in r.output


def test_export_labels_command(tmp_path):
    runner.invoke(app, ["generate", "--n", "2"])
    runner.invoke(app, ["run"])
    with Store(tmp_path / "docex.duckdb") as st:
        rid = st.latest_run_id()
        data = st.get_doc_detail(rid, "inv-0001")["extractions"][0]["data"]
        st.save_review(rid, "inv-0001", "correct", data)
    r = runner.invoke(app, ["export-labels"])
    assert r.exit_code == 0 and "Wrote 1 labels" in r.output
    assert (tmp_path / "labels" / "inv-0001.json").exists()
