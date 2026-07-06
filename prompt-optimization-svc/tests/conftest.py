"""Test fixtures using real Redis, MLflow, and Anthropic services.

Environment variables:
    POI_PROMPT_CACHE_REDIS_URL: Prompt cache Redis (default redis://localhost:6379/2)
    POI_MLFLOW_TRACKING_URI: MLflow URI (default http://localhost:5000)
    POI_ANTHROPIC_API_KEY: Anthropic API key
"""

import os

import pytest
import redis.asyncio as aioredis
from httpx import ASGITransport, AsyncClient

REDIS_URL = os.environ.get(
    "POI_PROMPT_CACHE_REDIS_URL",
    os.environ.get("POI_REDIS_URL", "redis://localhost:6379/2"),
)
MLFLOW_URI = os.environ.get("POI_MLFLOW_TRACKING_URI", "http://localhost:5000")
ANTHROPIC_API_KEY = os.environ.get("POI_ANTHROPIC_API_KEY", "")


# No-op markers — testcontainers always provides real Redis and MLflow.
# Kept as aliases so existing test imports continue to work.
requires_redis = pytest.mark.integration
requires_mlflow = pytest.mark.integration

requires_anthropic = pytest.mark.skipif(
    not ANTHROPIC_API_KEY, reason="POI_ANTHROPIC_API_KEY not set"
)


@pytest.fixture
async def real_redis():
    """Real async Redis connection (prompt cache DB)."""
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    yield r
    # Targeted cleanup — only test-prefixed keys
    for pattern in (
        "prompt:__test*",
        "tenant:__test*",
        "prompt:optimization:lock:__test*",
        "prompt:optimization:progress:__test*",
    ):
        async for key in r.scan_iter(match=pattern):
            await r.delete(key)
    await r.aclose()


@pytest.fixture
async def api_client():
    """Async test client — lifespan disabled to avoid external deps."""
    from app.main import app

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
