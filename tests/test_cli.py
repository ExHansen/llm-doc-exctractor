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
