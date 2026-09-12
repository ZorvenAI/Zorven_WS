"""H-03 · OCR retry queue.

Integration tests — real Redis. These exercise the actual sorted-set
operations and time-based dequeue logic.
"""

from __future__ import annotations

import time

import pytest
import redis.asyncio as aioredis

from app.cache.redis_manager import TenantKeys
from app.cache.retry_queue import (
    BACKOFF_SECONDS,
    MAX_ATTEMPTS,
    OCRRetryItem,
    dequeue_due,
    enqueue_retry,
    queue_size,
)

pytestmark = pytest.mark.integration

REDIS_URL = "redis://localhost:6379/2"


@pytest.fixture
async def redis_client():
    client = aioredis.from_url(REDIS_URL)
    yield client
    keys = await client.keys("oia:v1:test-retry:*")
    if keys:
        await client.delete(*keys)
    await client.aclose()


@pytest.fixture
def keys():
    return TenantKeys("test-retry")


def _item(**overrides) -> OCRRetryItem:
    base = dict(
        media_id="media-001",
        gcs_uri="gs://bucket/test.jpg",
        usage_tag="other",
        tenant_id="test-retry",
    )
    base.update(overrides)
    return OCRRetryItem(**base)


class TestOCRRetryItem:
    def test_json_roundtrip(self):
        item = _item()
        restored = OCRRetryItem.from_json(item.to_json())
        assert restored.media_id == item.media_id
        assert restored.gcs_uri == item.gcs_uri

    def test_default_max_attempts(self):
        item = _item()
        assert item.max_attempts == MAX_ATTEMPTS


class TestEnqueueDequeue:
    @pytest.mark.asyncio
    async def test_enqueue_and_dequeue(self, redis_client, keys):
        item = _item()
        result = await enqueue_retry(redis_client, keys, item)
        assert result is True
        assert item.attempt == 1

        size = await queue_size(redis_client, keys)
        assert size == 1

    @pytest.mark.asyncio
    async def test_max_attempts_exceeded_returns_false(self, redis_client, keys):
        item = _item(attempt=MAX_ATTEMPTS)
        result = await enqueue_retry(redis_client, keys, item)
        assert result is False

    @pytest.mark.asyncio
    async def test_dequeue_returns_empty_when_not_due(self, redis_client, keys):
        item = _item()
        await enqueue_retry(redis_client, keys, item)
        items = await dequeue_due(redis_client, keys)
        assert items == []

    @pytest.mark.asyncio
    async def test_dequeue_returns_due_items(self, redis_client, keys):
        item = _item()
        await enqueue_retry(redis_client, keys, item)

        key = keys.retry_queue("ocr")
        members = await redis_client.zrange(key, 0, -1, withscores=True)
        for member, _ in members:
            await redis_client.zadd(key, {member: time.time() - 1})

        items = await dequeue_due(redis_client, keys)
        assert len(items) == 1
        assert items[0].media_id == "media-001"

        size = await queue_size(redis_client, keys)
        assert size == 0

    @pytest.mark.asyncio
    async def test_backoff_increases_with_attempts(self, redis_client, keys):
        item1 = _item(media_id="m1")
        item2 = _item(media_id="m2", attempt=2)

        now = time.time()
        await enqueue_retry(redis_client, keys, item1)
        await enqueue_retry(redis_client, keys, item2)

        key = keys.retry_queue("ocr")
        members = await redis_client.zrange(key, 0, -1, withscores=True)

        scores = {
            OCRRetryItem.from_json(
                m.decode() if isinstance(m, bytes) else m
            ).media_id: s
            for m, s in members
        }

        assert scores["m2"] - now >= BACKOFF_SECONDS[2] - 1
        assert scores["m1"] - now >= BACKOFF_SECONDS[0] - 1

    @pytest.mark.asyncio
    async def test_queue_size(self, redis_client, keys):
        assert await queue_size(redis_client, keys) == 0

        await enqueue_retry(redis_client, keys, _item(media_id="a"))
        await enqueue_retry(redis_client, keys, _item(media_id="b"))

        assert await queue_size(redis_client, keys) == 2
