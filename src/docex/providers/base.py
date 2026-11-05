"""The provider contract every extractor (mock, local LLM, cloud LLM) implements."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from docex.results import ExtractionResult
from docex.schemas import DocumentMeta


class ExtractionProvider(Protocol):
    name: str
    model: str

    def extract(self, doc: DocumentMeta, schema: type[BaseModel], attempt: int) -> ExtractionResult:
        """Read one document and return JSON-native field values (strings, numbers, None).

        `attempt` starts at 1; later attempts are used for self-consistency checks.
        Implementations return status="failed" instead of raising for per-document problems.
        """
        ...
