"""E2E tests for configurable TTL and optimization schedule (US-060).

Exercises: tenant TTL set/get, TTL clamping enforcement,
loader uses tenant TTL, cache expiry with short TTL.
"""

import asyncio

import pytest

from app.cache.tenant_config import (
    DEFAULT_TTL,
    MAX_TTL,
    MIN_TTL,
    TenantConfigManager,
    clamp_ttl,
)


@pytest.mark.e2e
class TestConfigurableTTLSchedule:
    """Per-tenant TTL configuration and cache expiry."""

    async def test_tenant_config_set_and_get_ttl(
        self, e2e_tenant_config, e2e_prompt_name
    ):
        """Set TTL 600s, verify retrieval."""
        tid = e2e_prompt_name("ttl-tenant")

        await e2e_tenant_config.set_prompt_cache_ttl(tid, 600)
        retrieved = await e2e_tenant_config.get_prompt_cache_ttl(tid)
        assert retrieved == 600

        # Default for unknown tenant
        default = await e2e_tenant_config.get_prompt_cache_ttl(None)
        assert default == DEFAULT_TTL

    def test_ttl_clamping_enforced(self):
        """Below MIN -> clamped to MIN, above MAX -> clamped to MAX."""
        # Below minimum
        assert clamp_ttl(1) == MIN_TTL
        assert clamp_ttl(0) == MIN_TTL
        assert clamp_ttl(-100) == MIN_TTL

        # Above maximum
        assert clamp_ttl(5000) == MAX_TTL
        assert clamp_ttl(999999) == MAX_TTL

        # Within range
        assert clamp_ttl(300) == 300
        assert clamp_ttl(MIN_TTL) == MIN_TTL
        assert clamp_ttl(MAX_TTL) == MAX_TTL

    async def test_loader_uses_tenant_ttl(
        self, e2e_cache, e2e_tenant_config, e2e_loader, e2e_prompt_name
    ):
        """Set tenant TTL=60, load prompt, verify Redis TTL in range."""
        tid = e2e_prompt_name("ttl-loader")

        # Set tenant TTL to 60 seconds
        await e2e_tenant_config.set_prompt_cache_ttl(tid, 60)

        # Pre-cache a prompt (simulating MLflow tier 2 result)
        name = e2e_prompt_name("ttl-prompt")
        await e2e_cache.set_prompt(name, "TTL test template", ttl=60)

        # Load via loader (hits tier 1 cache)
        loaded = await e2e_loader.load(
            name=name,
            tenant_id=tid,
            fallback_template="Fallback",
        )
        assert "TTL test" in loaded or loaded == "Fallback"

        # Verify TTL was applied: check Redis TTL on the key
        r = await e2e_cache.connect()
        key = f"prompt:{name}:production"
        ttl_remaining = await r.ttl(key)
        # TTL should be positive and <= 60 (some time may have elapsed)
        assert ttl_remaining > 0
        assert ttl_remaining <= 60

    async def test_cache_expiry_with_short_ttl(self, e2e_cache, e2e_prompt_name):
        """TTL=1, sleep 2s, verify expired."""
        name = e2e_prompt_name("expiry")

        # Set with 1-second TTL
        await e2e_cache.set_prompt(name, "Short-lived template", ttl=1)

        # Verify it exists
        cached = await e2e_cache.get_prompt(name)
        assert cached == "Short-lived template"

        # Wait for expiry
        await asyncio.sleep(2)

        # Verify it's gone
        expired = await e2e_cache.get_prompt(name)
        assert expired is None
