"""OCR retry queue — Redis sorted set with exponential backoff.

Design §8.4 · implemented by story H-03.

When Cloud Vision and Gemini are both down, the captured media is queued
for a later attempt. The sorted set score is the Unix timestamp when the
item becomes eligible. A background task polls and drains the queue.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass

from app.cache.redis_manager import TenantKeys

logger = logging.getLogger(__name__)

QUEUE_NAME = "ocr"
MAX_ATTEMPTS = 4
BACKOFF_SECONDS = [30, 60, 120, 240]


@dataclass
class OCRRetryItem:
    """One item in the retry queue."""

    media_id: str
    gcs_uri: str
    usage_tag: str
    tenant_id: str
    attempt: int = 0
    max_attempts: int = MAX_ATTEMPTS

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, raw: str) -> OCRRetryItem:
        return cls(**json.loads(raw))


async def enqueue_retry(redis, keys: TenantKeys, item: OCRRetryItem) -> bool:
    """Add an item to the retry queue with exponential backoff.

    Returns False if max attempts exceeded (item is dropped).
    """
    if item.attempt >= item.max_attempts:
        logger.warning(
            "ocr_retry_max_attempts",
            extra={"media_id": item.media_id, "attempts": item.attempt},
        )
        return False

    backoff_idx = min(item.attempt, len(BACKOFF_SECONDS) - 1)
    delay = BACKOFF_SECONDS[backoff_idx]
    score = time.time() + delay

    key = keys.retry_queue(QUEUE_NAME)
    item.attempt += 1
    await redis.zadd(key, {item.to_json(): score})
    await redis.expire(key, 86400)
    return True


async def dequeue_due(redis, keys: TenantKeys) -> list[OCRRetryItem]:
    """Return items whose backoff has elapsed (score <= now)."""
    key = keys.retry_queue(QUEUE_NAME)
    now = time.time()

    raw_items = await redis.zrangebyscore(key, 0, now)
    if not raw_items:
        return []

    items = []
    for raw in raw_items:
        if isinstance(raw, bytes):
            raw = raw.decode()
        try:
            items.append(OCRRetryItem.from_json(raw))
        except (json.JSONDecodeError, TypeError):
            logger.warning("ocr_retry_corrupt_item", extra={"raw": raw})

    if items:
        await redis.zremrangebyscore(key, 0, now)

    return items


async def queue_size(redis, keys: TenantKeys) -> int:
    """Total items in the queue (for monitoring / J-02)."""
    key = keys.retry_queue(QUEUE_NAME)
    return await redis.zcard(key)
