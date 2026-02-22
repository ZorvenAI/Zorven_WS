"""Phase 1 contract test fixtures."""

import asyncio
from typing import Any

import pytest
from aiohttp import web

# ---------------------------------------------------------------------------
# Callback capture server — receives PATCH callbacks from orchestrator
# ---------------------------------------------------------------------------


class CallbackCapture:
    """Lightweight HTTP server that captures orchestrator callbacks.

    Runs on port 9999 inside the test process. The orchestrator's
    callback_url should point to http://host.docker.internal:9999/callback
    so the container can reach this server.
    """

    def __init__(self) -> None:
        self.callbacks: list[dict[str, Any]] = []
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None

    async def start(self) -> None:
        app = web.Application()
        app.router.add_patch("/callback", self._handle_callback)
        app.router.add_patch(
            "/api/v1/orchestration/jobs/{job_id}/callback/",
            self._handle_callback,
        )
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, "0.0.0.0", 9999)
        await self._site.start()

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()

    async def _handle_callback(self, request: web.Request) -> web.Response:
        payload = await request.json()
        self.callbacks.append(payload)
        return web.json_response({"status": "ok"})

    async def wait_for_callbacks(
        self, count: int, timeout: float = 30.0
    ) -> list[dict[str, Any]]:
        """Wait until at least `count` callbacks have arrived."""
        elapsed = 0.0
        interval = 0.3
        while len(self.callbacks) < count and elapsed < timeout:
            await asyncio.sleep(interval)
            elapsed += interval
        return self.callbacks


@pytest.fixture
async def callback_capture():
    """Start a callback capture server for the duration of a test."""
    server = CallbackCapture()
    await server.start()
    yield server
    await server.stop()
