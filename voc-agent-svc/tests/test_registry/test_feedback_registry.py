"""Tests for the FeedbackRegistry."""

import json

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.registry.feedback_registry import FeedbackRegistry
from app.registry.models import FeedbackItem


@pytest.fixture
def mock_redis():
    """Mock Redis client for registry operations."""
    redis = AsyncMock()
    redis.zadd = AsyncMock()
    redis.zcard = AsyncMock(return_value=42)
    redis.zrevrange = AsyncMock(return_value=[])
    redis.hset = AsyncMock()
    redis.hget = AsyncMock(return_value=None)
    redis.hgetall = AsyncMock(return_value={})
    redis.ttl = AsyncMock(return_value=-1)
    redis.expire = AsyncMock()
    redis.set = AsyncMock()
    return redis


@pytest.fixture
def registry(mock_redis):
    """FeedbackRegistry with mock Redis."""
    return FeedbackRegistry(redis_client=mock_redis, event_emitter=None)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_add_feedback(registry, mock_redis):
    """add_feedback calls zadd with serialized feedback."""
    item = FeedbackItem(
        feedback_id="test-001",
        text="Great product!",
    )
    await registry.add_feedback("test-tenant", item)
    mock_redis.zadd.assert_called_once()
    call_args = mock_redis.zadd.call_args
    key = call_args[0][0]
    assert "voca:test-tenant:registry:feedback" == key


@pytest.mark.asyncio
@pytest.mark.unit
async def test_get_feedback_count_no_redis():
    """get_feedback_count returns 0 when Redis is None."""
    reg = FeedbackRegistry(redis_client=None)
    count = await reg.get_feedback_count("test-tenant")
    assert count == 0


@pytest.mark.asyncio
@pytest.mark.unit
async def test_upsert_theme(registry, mock_redis):
    """upsert_theme calls hset with theme data."""
    theme_data = {"theme_name": "Product Quality", "severity_score": 7.5}
    await registry.upsert_theme("test-tenant", "product-quality", theme_data)
    mock_redis.hset.assert_called_once()
    call_args = mock_redis.hset.call_args
    key = call_args[0][0]
    field = call_args[0][1]
    assert key == "voca:test-tenant:registry:themes"
    assert field == "product-quality"
    stored_data = json.loads(call_args[0][2])
    assert stored_data["theme_name"] == "Product Quality"
