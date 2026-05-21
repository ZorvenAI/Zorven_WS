"""Test fixtures for prompt-optimization-svc."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def mock_redis():
    """Mock Redis client that returns healthy pings."""
    redis_mock = AsyncMock()
    redis_mock.ping.return_value = True
    redis_mock.get.return_value = None
    redis_mock.set.return_value = True
    redis_mock.aclose.return_value = None
    return redis_mock


@pytest.fixture
def mock_health_checker(mock_redis):
    """HealthChecker with mocked Redis."""
    from app.services.health_checker import HealthChecker

    return HealthChecker(redis_client=mock_redis)


@pytest.fixture
async def api_client():
    """Async test client for the FastAPI app."""
    # Patch Redis connection to avoid real connections during tests
    with patch("app.cache.redis_manager.aioredis") as mock_aioredis:
        mock_redis = AsyncMock()
        mock_redis.ping.return_value = True
        mock_redis.aclose.return_value = None
        mock_aioredis.from_url.return_value = mock_redis

        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            yield client
