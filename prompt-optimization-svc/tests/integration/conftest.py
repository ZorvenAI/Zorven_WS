"""Integration test fixtures — require real Redis and MLflow.

Run with: pytest tests/integration/ -v -m integration
Skip with: pytest tests/ -m "not integration"

Environment variables:
    POI_REDIS_URL: Redis URL (default redis://localhost:6379/2)
    POI_MLFLOW_TRACKING_URI: MLflow URI (default http://localhost:5000)
"""

import os

import pytest
import redis.asyncio as aioredis
from mlflow.tracking import MlflowClient

REDIS_URL = os.environ.get("POI_REDIS_URL", "redis://localhost:6379/2")
MLFLOW_URI = os.environ.get(
    "POI_MLFLOW_TRACKING_URI", "http://localhost:5000"
)


def _redis_available() -> bool:
    """Check if Redis is reachable."""
    import redis as sync_redis

    try:
        r = sync_redis.from_url(REDIS_URL)
        r.ping()
        r.close()
        return True
    except Exception:
        return False


def _mlflow_available() -> bool:
    """Check if MLflow tracking server is reachable."""
    try:
        import httpx

        resp = httpx.get(f"{MLFLOW_URI}/health", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


requires_redis = pytest.mark.skipif(
    not _redis_available(),
    reason=f"Redis not available at {REDIS_URL}",
)

requires_mlflow = pytest.mark.skipif(
    not _mlflow_available(),
    reason=f"MLflow not available at {MLFLOW_URI}",
)


@pytest.fixture
async def real_redis():
    """Real async Redis connection (DB 2 — prompt cache)."""
    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    yield r
    await r.aclose()


@pytest.fixture
def real_mlflow_client():
    """Real MLflow tracking client."""
    return MlflowClient(MLFLOW_URI)
