"""Phase 2 domain test fixtures — financial data and golden path helpers."""

import asyncio
from typing import Any

import pytest
from aiohttp import web

# ---------------------------------------------------------------------------
# Callback capture (reused from phase1, but isolated per test)
# ---------------------------------------------------------------------------


class CallbackCapture:
    """Captures orchestrator callbacks for golden path tests."""

    def __init__(self) -> None:
        self.callbacks: list[dict[str, Any]] = []
        self._runner: web.AppRunner | None = None

    async def start(self, port: int = 9998) -> None:
        app = web.Application()
        app.router.add_patch("/callback", self._handle)
        app.router.add_patch(
            "/api/v1/orchestration/jobs/{job_id}/callback/",
            self._handle,
        )
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", port)
        await site.start()

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()

    async def _handle(self, request: web.Request) -> web.Response:
        payload = await request.json()
        self.callbacks.append(payload)
        return web.json_response({"status": "ok"})

    async def wait_for_completed(self, timeout: float = 30.0) -> dict[str, Any] | None:
        """Wait for a 'completed' callback."""
        elapsed = 0.0
        while elapsed < timeout:
            for cb in self.callbacks:
                if cb.get("status") == "completed":
                    return cb
            await asyncio.sleep(0.3)
            elapsed += 0.3
        return None

    async def wait_for_callbacks(
        self, count: int, timeout: float = 30.0
    ) -> list[dict[str, Any]]:
        """Wait until at least `count` callbacks have arrived."""
        elapsed = 0.0
        while len(self.callbacks) < count and elapsed < timeout:
            await asyncio.sleep(0.3)
            elapsed += 0.3
        return self.callbacks


@pytest.fixture
async def callback_capture():
    """Start a callback capture server on port 9998."""
    server = CallbackCapture()
    await server.start(port=9998)
    yield server
    await server.stop()
