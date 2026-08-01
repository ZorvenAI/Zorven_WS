"""Fixtures backed by real services.

No mocks: the health probe is only worth testing against a Redis that is
genuinely up and a Redis that is genuinely down. A patched client would prove
the test double behaves, not the probe.
"""

from __future__ import annotations

import os
import socket

import pytest

REQUIRED_ENV = {
    "OIA_BACKEND_BASE_URL": "http://backend:8001",
    "OIA_GCS_BUCKET": "zorven-raw-assets",
}

REDIS_URL = os.environ.get("OIA_TEST_REDIS_URL", "redis://localhost:6379/2")


def _port_is_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def redis_available() -> bool:
    return _port_is_open("localhost", 6379)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(autouse=True)
def _required_env(monkeypatch):
    """Every test starts from a valid minimal configuration.

    Ambient OIA_ variables are cleared first: inheriting a developer's
    OIA_REDIS_URL would silently redirect the integration tests at a different
    database than the one under test.
    """
    for key in [k for k in os.environ if k.startswith("OIA_")]:
        monkeypatch.delenv(key, raising=False)
    for key, value in REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)
    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def app_with_live_redis(monkeypatch):
    """The real app wired to a real Redis."""
    if not redis_available():
        pytest.skip("Redis is not running on localhost:6379")
    monkeypatch.setenv("OIA_REDIS_URL", REDIS_URL)
    return _build_app()


@pytest.fixture
def app_with_dead_redis(monkeypatch):
    """The real app pointed at a port with nothing behind it.

    Not a simulated outage — a genuinely closed port, so the timeout path is
    the one the probe would take in production.
    """
    monkeypatch.setenv("OIA_REDIS_URL", f"redis://127.0.0.1:{free_port()}/2")
    return _build_app()


def _build_app():
    import importlib

    from app.core.config import get_settings

    get_settings.cache_clear()
    import app.main

    importlib.reload(app.main)
    return app.main.app
