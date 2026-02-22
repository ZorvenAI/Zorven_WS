"""Phase 3 stress test fixtures — concurrent helpers and callback capture."""

import asyncio
from typing import Any

import pytest
from aiohttp import web


class CallbackCapture:
    """Captures orchestrator callbacks for stress tests.

    Uses port 9997 to avoid conflicts with phase1/phase2 fixtures.
    """

    def __init__(self) -> None:
        self.callbacks: list[dict[str, Any]] = []
        self._runner: web.AppRunner | None = None

    async def start(self, port: int = 9997) -> None:
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

    async def wait_for_completed_count(
        self, count: int, timeout: float = 60.0
    ) -> list[dict[str, Any]]:
        """Wait until at least `count` 'completed' callbacks arrive."""
        elapsed = 0.0
        while elapsed < timeout:
            completed = [c for c in self.callbacks if c.get("status") == "completed"]
            if len(completed) >= count:
                return completed
            await asyncio.sleep(0.5)
            elapsed += 0.5
        return [c for c in self.callbacks if c.get("status") == "completed"]


@pytest.fixture
async def callback_capture():
    """Start a callback capture server on port 9997."""
    server = CallbackCapture()
    await server.start(port=9997)
    yield server
    await server.stop()
