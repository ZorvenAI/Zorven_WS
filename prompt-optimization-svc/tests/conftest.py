"""Test fixtures using real Redis and MLflow services.

Environment variables:
    POI_REDIS_URL: Redis URL (default redis://localhost:6379/2)
    POI_MLFLOW_TRACKING_URI: MLflow URI
    POI_ANTHROPIC_API_KEY: Anthropic API key
"""

import os

import pytest
import redis.asyncio as aioredis
from httpx import ASGITransport, AsyncClient

REDIS_URL = os.environ.get("POI_REDIS_URL", "redis://localhost:6379/2")
MLFLOW_URI = os.environ.get(
    "POI_MLFLOW_TRACKING_URI",
    "https://mlflow-server-production-4661.up.railway.app",
)
ANTHROPIC_API_KEY = os.environ.get("POI_ANTHROPIC_API_KEY", "")


def _redis_available() -> bool:
    import redis as sync_redis

    try:
        r = sync_redis.from_url(REDIS_URL)
        r.ping()
        r.close()
        return True
    except Exception:
        return False


def _mlflow_available() -> bool:
    try:
        import httpx

        resp = httpx.get(f"{MLFLOW_URI}/health", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


REDIS_AVAILABLE = _redis_available()
MLFLOW_AVAILABLE = _mlflow_available()

requires_redis = pytest.mark.skipif(
    not REDIS_AVAILABLE, reason=f"Redis not available at {REDIS_URL}"
)
requires_mlflow = pytest.mark.skipif(
    not MLFLOW_AVAILABLE, reason=f"MLflow not available at {MLFLOW_URI}"
)


@pytest.fixture
async def real_redis():
    """Real async Redis connection (DB 2 — prompt cache)."""
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    yield r
    async for key in r.scan_iter(match="*__test*"):
        await r.delete(key)
    await r.aclose()


@pytest.fixture
async def api_client():
    """Async test client for the FastAPI app."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        yield client
