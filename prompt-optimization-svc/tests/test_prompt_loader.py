"""Tests for ZorvenPromptLoader using real Redis + MLflow (US-010, US-012)."""

import pytest

from app.cache.prompt_cache import PromptCacheManager
from app.services.mlflow_registry import MLflowPromptRegistry
from app.services.prompt_loader import ZorvenPromptLoader, _convert_mlflow_template
from .conftest import MLFLOW_URI, REDIS_URL, requires_mlflow, requires_redis

TEST_PREFIX = "__test_loader_"


@requires_redis
class TestTier1CacheHit:
    @pytest.fixture
    async def loader(self):
        cache = PromptCacheManager(redis_url=REDIS_URL)
        await cache.connect()
        ldr = ZorvenPromptLoader(cache)
        yield ldr
        r = await cache.connect()
        async for key in r.scan_iter(match=f"prompt:{TEST_PREFIX}*"):
            await r.delete(key)
        await cache.close()

    async def test_cache_hit_production(self, loader):
        await loader.prompt_cache.set_prompt(
            f"{TEST_PREFIX}cached", "Cached template", ttl=10
        )
        result = await loader.load(f"{TEST_PREFIX}cached")
        assert result == "Cached template"

    async def test_tenant_override_checked_first(self, loader):
        await loader.prompt_cache.set_prompt(
            f"{TEST_PREFIX}tenant", "Global", ttl=10
        )
        await loader.prompt_cache.set_prompt(
            f"{TEST_PREFIX}tenant", "Tenant-specific", ttl=10, tenant_id="t-1"
        )
        result = await loader.load(f"{TEST_PREFIX}tenant", tenant_id="t-1")
        assert result == "Tenant-specific"

    async def test_falls_through_to_global(self, loader):
        await loader.prompt_cache.set_prompt(
            f"{TEST_PREFIX}global", "Global only", ttl=10
        )
        result = await loader.load(f"{TEST_PREFIX}global", tenant_id="t-miss")
        assert result == "Global only"


@requires_redis
class TestTier3Fallback:
    @pytest.fixture
    async def loader(self):
        cache = PromptCacheManager(redis_url=REDIS_URL)
        await cache.connect()
        ldr = ZorvenPromptLoader(cache)
        yield ldr
        await cache.close()

    async def test_all_miss_returns_fallback(self, loader):
        result = await loader.load(
            f"{TEST_PREFIX}nonexistent_xyz", fallback_template="Fallback text"
        )
        assert result == "Fallback text"

    async def test_empty_fallback_returns_empty(self, loader):
        result = await loader.load(f"{TEST_PREFIX}nonexistent_xyz")
        assert result == ""


@requires_redis
class TestTemplateFormatting:
    @pytest.fixture
    async def loader(self):
        cache = PromptCacheManager(redis_url=REDIS_URL)
        await cache.connect()
        ldr = ZorvenPromptLoader(cache)
        yield ldr
        r = await cache.connect()
        async for key in r.scan_iter(match=f"prompt:{TEST_PREFIX}*"):
            await r.delete(key)
        await cache.close()

    async def test_variables_applied(self, loader):
        await loader.prompt_cache.set_prompt(
            f"{TEST_PREFIX}fmt",
            "Analyze {{context.brand_name}} in {{context.industry}}",
            ttl=10,
        )
        result = await loader.load(
            f"{TEST_PREFIX}fmt",
            variables={"context.brand_name": "Acme", "context.industry": "tech"},
        )
        assert "Acme" in result
        assert "tech" in result

    async def test_no_variables_unchanged(self, loader):
        await loader.prompt_cache.set_prompt(
            f"{TEST_PREFIX}plain", "Plain template", ttl=10
        )
        result = await loader.load(f"{TEST_PREFIX}plain")
        assert result == "Plain template"


class TestMlflowTemplateConversion:
    def test_double_to_single(self):
        assert _convert_mlflow_template("{{var}}") == "{var}"

    def test_dotted(self):
        assert _convert_mlflow_template("{{context.brand_name}}") == "{context.brand_name}"

    def test_multiple(self):
        assert _convert_mlflow_template("{{a}} and {{b.c}}") == "{a} and {b.c}"

    def test_plain_unchanged(self):
        assert _convert_mlflow_template("plain text") == "plain text"

    def test_single_braces_unchanged(self):
        assert _convert_mlflow_template("{already_single}") == "{already_single}"


@requires_redis
class TestCacheInvalidation:
    @pytest.fixture
    async def loader(self):
        cache = PromptCacheManager(redis_url=REDIS_URL)
        await cache.connect()
        ldr = ZorvenPromptLoader(cache)
        yield ldr
        r = await cache.connect()
        async for key in r.scan_iter(match=f"prompt:{TEST_PREFIX}*"):
            await r.delete(key)
        await cache.close()

    async def test_invalidate_removes_cached(self, loader):
        await loader.prompt_cache.set_prompt(
            f"{TEST_PREFIX}inval", "Before", ttl=10
        )
        await loader.invalidate(f"{TEST_PREFIX}inval")
        result = await loader.load(
            f"{TEST_PREFIX}inval", fallback_template="After"
        )
        assert result == "After"

    async def test_invalidate_returns_zero_on_miss(self, loader):
        deleted = await loader.invalidate(f"{TEST_PREFIX}nope_xyz")
        assert deleted == 0
