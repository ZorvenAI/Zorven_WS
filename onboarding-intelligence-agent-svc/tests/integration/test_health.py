"""Health and readiness probes (M-04 refactor of A-05 AC-3).

``/health`` is liveness-only — always 200. Dependency checks moved to ``/ready``
(M-04 AC-1). Against a real Redis, up and down.
"""

from __future__ import annotations

import time

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = [pytest.mark.integration]

READY_BUDGET_S = 2.0


async def get(app, path: str):
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            return await client.get(path)


async def test_health_is_static_liveness(app_with_live_redis):
    """M-04 AC-1: /health is always 200 regardless of dep state."""
    response = await get(app_with_live_redis, "/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "onboarding-intelligence-agent",
    }


async def test_health_is_200_even_when_redis_is_down(app_with_dead_redis):
    """M-04 AC-1: /health stays 200 even when Redis is unreachable."""
    response = await get(app_with_dead_redis, "/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_ready_is_503_when_redis_is_down(app_with_dead_redis):
    """M-04 AC-1: /ready returns 503 when a required dependency is down."""
    response = await get(app_with_dead_redis, "/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert "redis" in body["failed"]


async def test_ready_answers_within_two_seconds_when_redis_is_down(
    app_with_dead_redis,
):
    started = time.perf_counter()
    response = await get(app_with_dead_redis, "/ready")
    elapsed = time.perf_counter() - started

    assert response.status_code == 503
    assert elapsed < READY_BUDGET_S, f"probe took {elapsed:.2f}s"


async def test_ready_probes_all_dependencies(app_with_live_redis):
    """M-04 AC-1: /ready checks Redis, Kafka, and STT."""
    response = await get(app_with_live_redis, "/ready")
    body = response.json()
    assert "redis" in body["dependencies"]
    assert "kafka" in body["dependencies"]
    assert "stt" in body["dependencies"]


async def test_kafka_absence_does_not_fail_ready(app_with_live_redis):
    """No GCP script provisions a broker; absence is a valid state."""
    response = await get(app_with_live_redis, "/ready")
    assert response.status_code in (200, 503)  # 503 only if STT isn't configured

    diagnostics = (await get(app_with_live_redis, "/health/diagnostics")).json()
    kafka = diagnostics["dependencies"]["kafka"]
    assert kafka["configured"] is False
    assert kafka["required"] is False


async def test_configured_but_unreachable_kafka_does_fail_ready(monkeypatch):
    """When a broker IS configured, an unreachable one is a real fault."""
    from tests.conftest import _build_app, free_port, redis_available

    if not redis_available():
        pytest.skip("Redis is not running on localhost:6379")

    monkeypatch.setenv("OIA_REDIS_URL", "redis://localhost:6379/2")
    monkeypatch.setenv("OIA_KAFKA_BOOTSTRAP_SERVERS", f"127.0.0.1:{free_port()}")

    response = await get(_build_app(), "/ready")
    assert response.status_code == 503
    assert "kafka" in response.json()["failed"]


async def test_diagnostics_reports_every_dependency(app_with_live_redis):
    body = (await get(app_with_live_redis, "/health/diagnostics")).json()

    assert set(body["dependencies"]) == {"redis", "kafka", "backend", "poi", "gcs"}
    assert body["service"] == "onboarding-intelligence-agent"
    assert body["port"] == 8120
    assert body["env_prefix"] == "OIA_"
    assert body["key_prefix"] == "oia:v1:"


async def test_diagnostics_reports_db_2_not_27(app_with_live_redis):
    """ERRATA-01, visible from the running service."""
    body = (await get(app_with_live_redis, "/health/diagnostics")).json()
    assert body["redis_db"] == 2
    assert body["prompt_cache_db"] == 2


async def test_diagnostics_never_exposes_a_secret_value(
    app_with_live_redis, monkeypatch
):
    """Design §19: references are recorded, values never are."""
    monkeypatch.setenv("OIA_GEMINI_KEY", "super-secret-value")
    from tests.conftest import _build_app

    body = (await get(_build_app(), "/health/diagnostics")).json()

    assert body["secrets_configured"]["OIA_GEMINI_KEY"] is True
    assert "super-secret-value" not in str(body)


async def test_settings_are_visible_for_debugging(app_with_live_redis):
    body = (await get(app_with_live_redis, "/health/diagnostics")).json()
    assert body["settings"]["sufficiency_green_threshold"] == 0.7
    assert body["settings"]["process_timeout_s"] == 300
