"""Integration test fixtures — backed by testcontainers (US-059).

Containers are managed by session-scoped fixtures in
tests/conftest_testcontainers.py. This conftest reads connection
URLs from environment variables set by those fixtures.

Run with: pytest tests/integration/ -v -m integration
"""

import os

import pytest
import redis.asyncio as aioredis
from mlflow.tracking import MlflowClient

REDIS_URL = os.environ.get(
    "POI_PROMPT_CACHE_REDIS_URL",
    os.environ.get("POI_REDIS_URL", "redis://localhost:6379/2"),
)
MLFLOW_URI = os.environ.get("POI_MLFLOW_TRACKING_URI", "http://localhost:5000")

# No-op markers — testcontainers always provides real Redis and MLflow.
# Kept as aliases so existing test imports continue to work.
requires_redis = pytest.mark.integration
requires_mlflow = pytest.mark.integration


@pytest.fixture
async def real_redis():
    """Real async Redis connection (prompt cache DB)."""
    url = os.environ.get("POI_PROMPT_CACHE_REDIS_URL", REDIS_URL)
    r = aioredis.from_url(url, decode_responses=True)
    yield r
    await r.aclose()


@pytest.fixture
def real_mlflow_client():
    """Real MLflow tracking client."""
    uri = os.environ.get("POI_MLFLOW_TRACKING_URI", MLFLOW_URI)
    return MlflowClient(uri)
