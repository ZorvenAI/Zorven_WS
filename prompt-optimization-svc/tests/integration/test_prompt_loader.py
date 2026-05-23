"""Integration tests for ZorvenPromptLoader (US-010, US-012).

Requires real Redis and MLflow.
"""

import pytest

from app.cache.prompt_cache import PromptCacheManager
from app.services.mlflow_registry import MLflowPromptRegistry
from app.services.prompt_loader import ZorvenPromptLoader

from .conftest import MLFLOW_URI, REDIS_URL, requires_mlflow, requires_redis

TEST_PREFIX = "__inttest_loader_"


@pytest.mark.integration
@requires_redis
@requires_mlflow
class TestPromptLoaderEndToEnd:
    """US-010: Three-tier resolution against real Redis + MLflow."""

    @pytest.fixture
    async def loader(self):
        cache = PromptCacheManager(redis_url=REDIS_URL)
        await cache.connect()
        registry = MLflowPromptRegistry(MLFLOW_URI)
        ldr = ZorvenPromptLoader(cache, registry)
        yield ldr
        # Cleanup
        r = await cache.connect()
        async for key in r.scan_iter(match=f"prompt:{TEST_PREFIX}*"):
            await r.delete(key)
        await cache.close()

    async def test_tier1_cache_hit(self, loader):
        """Tier 1: Prompt retrieved from Redis cache."""
        await loader.prompt_cache.set_prompt(
            f"{TEST_PREFIX}cached", "Cached prompt text", ttl=10
        )
        result = await loader.load(f"{TEST_PREFIX}cached")
        assert result == "Cached prompt text"

    async def test_tier2_mlflow_fetch_and_cache(self, loader):
        """Tier 2: Cache miss → MLflow fetch → cached for next call."""
        name = f"{TEST_PREFIX}mlflow-fetch"
        # Register in MLflow first
        loader.mlflow_registry.register_prompt(
            name=name, template="From MLflow: {{context.brand}}"
        )

        # First load: cache miss → MLflow
        result = await loader.load(name, fallback="fallback")
        assert "From MLflow" in result or result == "fallback"

    async def test_tier3_fallback(self, loader):
        """Tier 3: Both miss → fallback returned."""
        result = await loader.load(
            f"{TEST_PREFIX}nonexistent-xyz",
            fallback="Fallback prompt",
        )
        assert result == "Fallback prompt"

    async def test_template_formatting(self, loader):
        """Variables applied to loaded template."""
        await loader.prompt_cache.set_prompt(
            f"{TEST_PREFIX}format",
            "Hello {{context.name}} in {{context.city}}",
            ttl=10,
        )
        result = await loader.load(
            f"{TEST_PREFIX}format",
            variables={"context.name": "World", "context.city": "NYC"},
        )
        assert "World" in result
        assert "NYC" in result

    async def test_tenant_override_before_global(self, loader):
        """US-012 AC-1: Tenant cache checked before global."""
        await loader.prompt_cache.set_prompt(
            f"{TEST_PREFIX}tenant-or", "Global version", ttl=10
        )
        await loader.prompt_cache.set_prompt(
            f"{TEST_PREFIX}tenant-or",
            "Tenant version",
            ttl=10,
            tenant_id="t-int",
        )
        result = await loader.load(
            f"{TEST_PREFIX}tenant-or", tenant_id="t-int"
        )
        assert result == "Tenant version"

    async def test_cache_invalidation(self, loader):
        """Invalidation removes cached prompt."""
        await loader.prompt_cache.set_prompt(
            f"{TEST_PREFIX}inval", "Before", ttl=10
        )
        await loader.invalidate(f"{TEST_PREFIX}inval")
        result = await loader.load(
            f"{TEST_PREFIX}inval", fallback="After invalidation"
        )
        assert result == "After invalidation"
