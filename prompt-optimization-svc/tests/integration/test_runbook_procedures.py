"""Integration tests verifying documented runbook procedures (US-061).

Tests that documented operational procedures actually work
against real Redis and real service components.
"""

import time

import pytest

from app.cache.prompt_cache import PromptCacheManager
from app.logic.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitState,
    MLflowCircuitBreaker,
)


@pytest.mark.integration
class TestRunbookProcedures:
    """Verify documented operational procedures work correctly."""

    async def test_cache_flush_procedure(self):
        """Follow documented Redis flush steps, verify keys cleared.

        Runbook Section 3: Redis Cache Flush
        - Set test keys matching documented patterns
        - Call invalidate_prompt()
        - Verify all keys deleted
        """
        import os

        url = os.environ.get("POI_PROMPT_CACHE_REDIS_URL", "redis://localhost:6379/2")
        cache = PromptCacheManager(redis_url=url)
        await cache.connect()

        try:
            name = "__test_runbook_flush"

            # Set keys matching documented patterns
            await cache.set_prompt(name, "Production template", ttl=300)
            await cache.set_prompt(
                name, "Tenant A template", tenant_id="tenant-a", ttl=300
            )

            # Verify keys exist
            assert await cache.get_prompt(name) == "Production template"
            assert (
                await cache.get_prompt(name, tenant_id="tenant-a")
                == "Tenant A template"
            )

            # Follow documented flush procedure: invalidate_prompt()
            deleted = await cache.invalidate_prompt(name)
            assert deleted >= 1

            # Verify all cached versions cleared
            assert await cache.get_prompt(name) is None
            assert await cache.get_prompt(name, tenant_id="tenant-a") is None
        finally:
            await cache.close()

    def test_circuit_breaker_recovery_procedure(self):
        """Follow documented circuit breaker recovery steps.

        Runbook Section 2: MLflow Recovery and Circuit Breaker
        - Start in CLOSED state
        - Record failures to trigger OPEN
        - Wait for probe interval to reach HALF_OPEN
        - Record success to recover to CLOSED
        """
        config = CircuitBreakerConfig(
            failure_threshold_seconds=1,
            half_open_interval_seconds=1,
        )
        breaker = MLflowCircuitBreaker(config)

        # Step 1: Verify starts CLOSED (documented)
        assert breaker.state == CircuitState.CLOSED
        assert breaker.should_allow_request() is True

        # Step 2: Simulate sustained failures -> OPEN (documented: >=5min, using 1s for test)
        breaker.record_failure()
        time.sleep(1.1)
        breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        # Step 3: Wait for probe interval -> HALF_OPEN (documented: 60s, using 1s for test)
        time.sleep(1.1)
        allowed = breaker.should_allow_request()
        assert allowed is True
        assert breaker.state == CircuitState.HALF_OPEN

        # Step 4: Record success -> CLOSED (documented recovery)
        breaker.record_success()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.should_allow_request() is True

    async def test_health_endpoint_response_format(self):
        """Verify /health response matches documented JSON format.

        Runbook Section 1: Health Endpoint
        - Response has 'status' field
        - Response has 'dependencies' array
        - Each dependency has 'name' and 'status' fields
        """
        from httpx import ASGITransport, AsyncClient

        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()

        # Documented fields
        assert "status" in data
        assert data["status"] in ("healthy", "degraded", "unhealthy")

        assert "dependencies" in data
        assert isinstance(data["dependencies"], list)

        # Each dependency has documented structure
        for dep in data["dependencies"]:
            assert "name" in dep
            assert "status" in dep
            assert dep["status"] in ("up", "down", "disabled")
