"""Integration tests for rate limiting — requires running Redis."""

import pytest

from app.cache.redis_manager import RedisManager

pytestmark = pytest.mark.integration


class TestRateLimitingIntegration:
    async def test_first_request_allowed(self, redis_manager: RedisManager):
        result = await redis_manager.check_rate_limit(
            "integration-test-tenant", limit=5
        )
        assert result is True

    async def test_rate_limit_enforcement(self, redis_manager: RedisManager):
        tenant_id = "rate-limit-test-tenant"
        limit = 3

        # First 3 requests should be allowed
        for i in range(limit):
            result = await redis_manager.check_rate_limit(tenant_id, limit=limit)
            assert result is True, f"Request {i + 1} should be allowed"

        # 4th request should be blocked
        result = await redis_manager.check_rate_limit(tenant_id, limit=limit)
        assert result is False, "Request over limit should be blocked"
