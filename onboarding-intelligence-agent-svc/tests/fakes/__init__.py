"""Shared provider fakes for the OIA test suite."""

from tests.fakes.models import (
    FakeSTTAdapter,
    FakeVisionProvider,
    StubModels,
    llm_for_stub,
)

__all__ = [
    "FakeSTTAdapter",
    "FakeVisionProvider",
    "StubModels",
    "llm_for_stub",
]
