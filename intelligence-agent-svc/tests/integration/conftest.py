"""Integration test fixtures requiring real Redis."""

import pytest

from app.cache.redis_manager import RedisManager


@pytest.fixture
async def redis_manager():
    """Real Redis manager for integration tests."""
    manager = RedisManager("redis://localhost:6379/3")
    yield manager
    # Clean up test keys
    try:
        r = await manager._get_redis()
        keys = []
        async for key in r.scan_iter("intel:*"):
            keys.append(key)
        if keys:
            await r.delete(*keys)
    except Exception:
        pass
    await manager.close()
