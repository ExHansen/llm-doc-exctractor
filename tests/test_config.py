from pathlib import Path

from docex.config import Settings


def test_settings_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("DOCEX_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DOCEX_REVIEW_THRESHOLD", "0.8")
    s = Settings()
    assert s.review_threshold == 0.8
    assert s.resolved_db_path == tmp_path / "docex.duckdb"


def test_settings_defaults(monkeypatch):
    for k in ("DOCEX_DATA_DIR", "DOCEX_REVIEW_THRESHOLD", "DOCEX_DB_PATH"):
        monkeypatch.delenv(k, raising=False)
    s = Settings(_env_file=None)
    assert s.data_dir == Path("data") and s.provider == "mock" and s.seed == 42
    assert s.consistency_runs == 2 and s.review_threshold == 0.7
    assert (s.mock_base_error_rate, s.mock_consistency_correlation, s.mock_failure_rate) == (
        0.03,
        0.5,
        0.01,
    )
