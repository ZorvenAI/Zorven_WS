"""Hypothesis property tests for Redis cache via testcontainers (US-059).

Property-based tests that verify cache invariants hold for arbitrary
inputs against a real Redis container.
"""

import os

import pytest
from hypothesis import given, settings as h_settings, HealthCheck
from hypothesis import strategies as st

from app.cache.prompt_cache import PromptCacheManager

TEST_PREFIX = "__tc_prop_"


@pytest.mark.integration
@pytest.mark.property
class TestRedisPropertiesTC:
    """Hypothesis property tests against real Redis."""

    @pytest.fixture
    async def cache(self):
        url = os.environ.get("POI_PROMPT_CACHE_REDIS_URL", "redis://localhost:6379/2")
        mgr = PromptCacheManager(redis_url=url)
        await mgr.connect()
        yield mgr
        # Cleanup test keys
        r = await mgr.connect()
        async for key in r.scan_iter(match=f"prompt:{TEST_PREFIX}*"):
            await r.delete(key)
        async for key in r.scan_iter(match=f"prompt:optimization:lock:{TEST_PREFIX}*"):
            await r.delete(key)
        await mgr.close()

    @given(
        name_suffix=st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N"),
                whitelist_characters="-_",
            ),
            min_size=1,
            max_size=50,
        ),
        template=st.text(min_size=1, max_size=200),
    )
    @h_settings(
        max_examples=15,
        deadline=10000,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    async def test_any_prompt_name_roundtrips(self, cache, name_suffix, template):
        """Any valid prompt name set/get round-trips correctly."""
        key = f"{TEST_PREFIX}{name_suffix}"
        await cache.set_prompt(key, template, ttl=30)
        result = await cache.get_prompt(key)
        assert result == template
        await cache.invalidate_prompt(key)

    @given(
        tenant_a=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N")),
            min_size=1,
            max_size=20,
        ),
        tenant_b=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N")),
            min_size=1,
            max_size=20,
        ),
    )
    @h_settings(
        max_examples=15,
        deadline=10000,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    async def test_any_tenant_id_isolates_cache(self, cache, tenant_a, tenant_b):
        """Any two different tenant IDs never cross-read cached prompts."""
        from hypothesis import assume

        assume(tenant_a != tenant_b)

        key = f"{TEST_PREFIX}iso-prop"
        await cache.set_prompt(key, "tenant-a-data", ttl=30, tenant_id=tenant_a)
        result = await cache.get_prompt(key, tenant_id=tenant_b)
        assert result is None
        await cache.invalidate_prompt(key)

    @given(
        owner_a=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N")),
            min_size=1,
            max_size=20,
        ),
        owner_b=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N")),
            min_size=1,
            max_size=20,
        ),
    )
    @h_settings(
        max_examples=15,
        deadline=10000,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    async def test_lock_acquire_rejects_second_owner(self, cache, owner_a, owner_b):
        """Any two different owners — second acquire always fails."""
        from hypothesis import assume

        assume(owner_a != owner_b)

        group = f"{TEST_PREFIX}lock-prop"
        # Ensure clean state
        await cache.release_optimization_lock(group, owner_a)

        acquired = await cache.acquire_optimization_lock(group, owner_a, ttl=30)
        assert acquired is True
        second = await cache.acquire_optimization_lock(group, owner_b, ttl=30)
        assert second is False
        await cache.release_optimization_lock(group, owner_a)
