import pytest

from docex.config import Settings
from docex.providers.registry import get_provider


def test_registry(tmp_path):
    provider = get_provider("mock", Settings(data_dir=tmp_path, mock_base_error_rate=0.2))
    assert provider.name == "mock" and provider.model == "mock-v1"
    with pytest.raises(ValueError, match="Available: mock"):
        get_provider("ollama", Settings(data_dir=tmp_path))
