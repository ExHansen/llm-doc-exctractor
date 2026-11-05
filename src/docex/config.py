"""Runtime settings, read from DOCEX_* environment variables and an optional .env file."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DOCEX_", env_file=".env", extra="ignore")

    data_dir: Path = Path("data")
    db_path: Path | None = None
    reports_dir: Path = Path("reports")
    provider: str = "mock"
    seed: int = 42
    consistency_runs: int = 2
    review_threshold: float = 0.7
    mock_base_error_rate: float = 0.03
    mock_consistency_correlation: float = 0.5
    mock_failure_rate: float = 0.01

    @property
    def resolved_db_path(self) -> Path:
        return self.db_path or self.data_dir / "docex.duckdb"
