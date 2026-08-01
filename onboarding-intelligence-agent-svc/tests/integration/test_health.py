"""AC-3 — the health probe is honest.

Against a real Redis, up and down. The interesting case is down: a probe that
reports optimism, or hangs, is worse than no probe, because Cloud Run's health
check and the CI post-deploy check both believe it.
"""

from __future__ import annotations

import time

import pytest
from httpx import ASGITransport, AsyncClient

pytestmark = [pytest.mark.integration]

HEALTH_BUDGET_S = 2.0


async def get(app, path: str):
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            return await client.get(path)


async def test_health_is_200_when_redis_is_up(app_with_live_redis):
    response = await get(app_with_live_redis, "/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "onboarding-intelligence-agent",
    }


async def test_health_is_503_when_redis_is_down(app_with_dead_redis):
    response = await get(app_with_dead_redis, "/health")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unhealthy"
    assert "redis" in body["failed"]


async def test_health_answers_within_two_seconds_when_redis_is_down(
    app_with_dead_redis,
):
    """AC-3: returns 503 within 2 s rather than hanging."""
    started = time.perf_counter()
    response = await get(app_with_dead_redis, "/health")
    elapsed = time.perf_counter() - started

    assert response.status_code == 503
    assert elapsed < HEALTH_BUDGET_S, f"probe took {elapsed:.2f}s"


async def test_kafka_absence_does_not_fail_health(app_with_live_redis):
    """No GCP script provisions a broker; absence is a valid state.

    A literal reading of AC-3 would make the service permanently 503 in
    production, where no Kafka exists at all.
    """
    response = await get(app_with_live_redis, "/health")
    assert response.status_code == 200

    diagnostics = (await get(app_with_live_redis, "/health/diagnostics")).json()
    kafka = diagnostics["dependencies"]["kafka"]
    assert kafka["configured"] is False
    assert kafka["required"] is False
    assert "not configured" in kafka["detail"]


async def test_configured_but_unreachable_kafka_does_fail_health(monkeypatch):
    """When a broker IS configured, an unreachable one is a real fault."""
    from tests.conftest import _build_app, free_port, redis_available

    if not redis_available():
        pytest.skip("Redis is not running on localhost:6379")

    monkeypatch.setenv("OIA_REDIS_URL", "redis://localhost:6379/2")
    monkeypatch.setenv("OIA_KAFKA_BOOTSTRAP_SERVERS", f"127.0.0.1:{free_port()}")

    response = await get(_build_app(), "/health")
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
