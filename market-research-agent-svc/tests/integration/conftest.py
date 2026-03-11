"""Integration test fixtures requiring Redis."""

import pytest

from app.cache.redis_manager import RedisManager


@pytest.fixture
async def redis_manager():
    """Real Redis connection for integration tests."""
    manager = RedisManager("redis://localhost:6379/11")
    yield manager
    # Clean up test keys
    try:
        r = await manager._get_redis()
        keys = []
        async for key in r.scan_iter("mra:*"):
            keys.append(key)
        if keys:
            await r.delete(*keys)
    except Exception:
        pass
    await manager.close()
