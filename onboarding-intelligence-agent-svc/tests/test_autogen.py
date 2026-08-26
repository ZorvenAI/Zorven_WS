"""J-06 — ProcessExecutor auto-generation of brand strategy and identity.

Covers _auto_generate behaviour: both succeed, partial failure, opt-out
via ProcessOptions, missing company_id, and unconfigured backend.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.logic.process_executor import ProcessExecutor
from app.messaging.schemas import ProcessOptions

pytestmark = pytest.mark.unit


class FakeBackend:
    """Minimal stand-in that records calls and returns configurable results."""

    def __init__(
        self,
        *,
        strategy_result: dict[str, Any] | None = {"success": True},
        identity_result: dict[str, Any] | None = {"success": True},
        strategy_error: Exception | None = None,
        identity_error: Exception | None = None,
    ) -> None:
        self._strategy_result = strategy_result
        self._identity_result = identity_result
        self._strategy_error = strategy_error
        self._identity_error = identity_error
        self.strategy_calls: list[dict[str, Any]] = []
        self.identity_calls: list[dict[str, Any]] = []
        self.configured = True

    async def generate_brand_strategy(
        self, *, tenant_id: str, company_id: int
    ) -> dict[str, Any] | None:
        self.strategy_calls.append({"tenant_id": tenant_id, "company_id": company_id})
        if self._strategy_error:
            raise self._strategy_error
        return self._strategy_result

    async def generate_brand_identity(
        self, *, tenant_id: str, company_id: int
    ) -> dict[str, Any] | None:
        self.identity_calls.append({"tenant_id": tenant_id, "company_id": company_id})
        if self._identity_error:
            raise self._identity_error
        return self._identity_result


class FakeRedis:
    """Enough to construct a ProcessExecutor without a real pool."""

    def keys_for(self, tenant_id: str) -> Any:
        return type("Keys", (), {"idempotency": lambda self, k: f"idem:{k}"})()

    @property
    def client(self) -> Any:
        return None


def _executor(backend: FakeBackend | None = None) -> ProcessExecutor:
    return ProcessExecutor(
        redis=FakeRedis(),  # type: ignore[arg-type]
        backend=backend,
    )


async def test_auto_generate_both_succeed():
    backend = FakeBackend()
    ex = _executor(backend)

    generated = await ex._auto_generate(
        tenant_id="t-1", company_id=42, options={}, job_id="j-1"
    )

    assert generated == ["brand_strategy", "brand_identity"]
    assert len(backend.strategy_calls) == 1
    assert len(backend.identity_calls) == 1
    assert backend.strategy_calls[0]["company_id"] == 42


async def test_auto_generate_strategy_only():
    backend = FakeBackend()
    ex = _executor(backend)

    generated = await ex._auto_generate(
        tenant_id="t-1",
        company_id=42,
        options={"auto_generate_identity": False},
        job_id="j-1",
    )

    assert generated == ["brand_strategy"]
    assert len(backend.identity_calls) == 0


async def test_auto_generate_identity_only():
    backend = FakeBackend()
    ex = _executor(backend)

    generated = await ex._auto_generate(
        tenant_id="t-1",
        company_id=42,
        options={"auto_generate_strategy": False},
        job_id="j-1",
    )

    assert generated == ["brand_identity"]
    assert len(backend.strategy_calls) == 0


async def test_auto_generate_both_disabled():
    backend = FakeBackend()
    ex = _executor(backend)

    generated = await ex._auto_generate(
        tenant_id="t-1",
        company_id=42,
        options={
            "auto_generate_strategy": False,
            "auto_generate_identity": False,
        },
        job_id="j-1",
    )

    assert generated == []
    assert len(backend.strategy_calls) == 0
    assert len(backend.identity_calls) == 0


async def test_auto_generate_strategy_fails_identity_succeeds():
    """AC-2: partial failure — one fails, the other succeeds."""
    backend = FakeBackend(strategy_error=RuntimeError("AI down"))
    ex = _executor(backend)

    generated = await ex._auto_generate(
        tenant_id="t-1", company_id=42, options={}, job_id="j-1"
    )

    assert generated == ["brand_identity"]


async def test_auto_generate_strategy_returns_none():
    """Backend returning None (e.g. breaker open) is not an exception."""
    backend = FakeBackend(strategy_result=None)
    ex = _executor(backend)

    generated = await ex._auto_generate(
        tenant_id="t-1", company_id=42, options={}, job_id="j-1"
    )

    assert generated == ["brand_identity"]


async def test_auto_generate_no_backend():
    """No backend configured → empty list, no crash."""
    ex = _executor(backend=None)

    generated = await ex._auto_generate(
        tenant_id="t-1", company_id=42, options={}, job_id="j-1"
    )

    assert generated == []


async def test_process_options_defaults():
    """Both auto_generate flags default to True."""
    opts = ProcessOptions()

    assert opts.auto_generate_strategy is True
    assert opts.auto_generate_identity is True


async def test_process_options_explicit_false():
    """Explicit False disables generation."""
    opts = ProcessOptions(
        auto_generate_strategy=False,
        auto_generate_identity=False,
    )

    assert opts.auto_generate_strategy is False
    assert opts.auto_generate_identity is False


async def test_wf2_failure_does_not_fail_process():
    """AC-2: generation failure → SUCCEEDED with generated: []."""
    backend = FakeBackend(
        strategy_error=RuntimeError("AI service down"),
        identity_error=RuntimeError("AI service down"),
    )
    ex = _executor(backend)

    generated = await ex._auto_generate(
        tenant_id="t-1", company_id=42, options={}, job_id="j-1"
    )

    assert generated == []
