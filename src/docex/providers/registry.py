"""Provider registry: add a provider by writing one class and one entry in PROVIDERS."""

from __future__ import annotations

from collections.abc import Callable

from docex.config import Settings
from docex.providers.base import ExtractionProvider
from docex.providers.mock import MockProvider

PROVIDERS: dict[str, Callable[[Settings], ExtractionProvider]] = {
    "mock": lambda s: MockProvider(
        s.data_dir,
        s.seed,
        s.mock_base_error_rate,
        s.mock_consistency_correlation,
        s.mock_failure_rate,
    ),
}


def get_provider(name: str, settings: Settings) -> ExtractionProvider:
    try:
        factory = PROVIDERS[name]
    except KeyError:
        available = ", ".join(sorted(PROVIDERS))
        raise ValueError(f"Unknown provider '{name}'. Available: {available}") from None
    return factory(settings)
