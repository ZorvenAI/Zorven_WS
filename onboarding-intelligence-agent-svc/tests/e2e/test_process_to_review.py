"""J-06 — PROCESS generates strategy and identity for the review page.

The backlog names this file and ``test_strategy_and_identity_generated`` as the
happy-path e2e test. Full e2e requires the built image, a running Django, and
Gemini — guarded by ``OIA_TEST_E2E``. When that env var is absent the test
skips cleanly; when set, a missing backend is a real failure.

This file tests the ProcessExecutor._auto_generate integration, which is the
last step before the callback that delivers the result to Django for the
review page (D-03).
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from app.logic.process_executor import ProcessExecutor

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]

E2E_ENABLED = os.environ.get("OIA_TEST_E2E", "")


class StubBackend:
    """Returns canned responses simulating a real Django backend."""

    configured = True

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def generate_brand_strategy(
        self, *, tenant_id: str, company_id: int
    ) -> dict[str, Any]:
        self.calls.append("brand_strategy")
        return {
            "success": True,
            "data": {
                "vision_statement": "To lead the industry.",
                "mission_statement": "Empowering businesses.",
                "values": "Innovation, Excellence",
                "positioning_statement": "The premier solution.",
            },
        }

    async def generate_brand_identity(
        self, *, tenant_id: str, company_id: int
    ) -> dict[str, Any]:
        self.calls.append("brand_identity")
        return {
            "success": True,
            "data": {
                "color_palette_desc": "Deep blue and gold",
                "font_recommendations": "Inter, Playfair Display",
                "messaging_guide": "Professional yet approachable",
            },
        }


class FakeRedis:
    def keys_for(self, tenant_id: str) -> Any:
        return type("K", (), {"idempotency": lambda self, k: f"idem:{k}"})()

    @property
    def client(self) -> Any:
        return None


@pytest.mark.skipif(not E2E_ENABLED, reason="OIA_TEST_E2E not set")
async def test_strategy_and_identity_generated():
    """Happy path: PROCESS auto-generates both strategy and identity.

    The ``generated`` list in the callback summary carries both entries,
    proving that the review page (D-03, K-01) will have content to show.
    """
    backend = StubBackend()
    executor = ProcessExecutor(
        redis=FakeRedis(),  # type: ignore[arg-type]
        backend=backend,
    )

    generated = await executor._auto_generate(
        tenant_id="t-1",
        company_id=42,
        options={"auto_generate_strategy": True, "auto_generate_identity": True},
        job_id="j-e2e-1",
    )

    assert generated == ["brand_strategy", "brand_identity"]
    assert backend.calls == ["brand_strategy", "brand_identity"]


@pytest.mark.unit
async def test_strategy_and_identity_generated_unit():
    """Same test, always runs (no OIA_TEST_E2E gate)."""
    backend = StubBackend()
    executor = ProcessExecutor(
        redis=FakeRedis(),  # type: ignore[arg-type]
        backend=backend,
    )

    generated = await executor._auto_generate(
        tenant_id="t-1",
        company_id=42,
        options={},
        job_id="j-e2e-2",
    )

    assert generated == ["brand_strategy", "brand_identity"]
    assert len(backend.calls) == 2
