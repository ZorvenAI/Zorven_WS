"""E2E test fixtures wiring real services into pipeline-ready objects (US-060).

All fixtures connect to real Redis, MLflow, and PostgreSQL via
testcontainer or Railway URLs from POI_* environment variables.
"""

import os
import uuid

import pytest
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.cache.prompt_cache import PromptCacheManager
from app.cache.tenant_config import TenantConfigManager
from app.logic.canary_manager import CanaryManager
from app.logic.circuit_breaker import CircuitBreakerConfig, MLflowCircuitBreaker
from app.logic.lifecycle import PromptLifecycleManager
from app.logic.run_lifecycle import RunLifecycleManager
from app.services.mlflow_registry import MLflowPromptRegistry
from app.services.prompt_loader import ZorvenPromptLoader

E2E_PREFIX = "__e2e_"


@pytest.fixture
def e2e_registry():
    """MLflowPromptRegistry connected to real MLflow."""
    uri = os.environ.get("POI_MLFLOW_TRACKING_URI", "http://localhost:5000")
    return MLflowPromptRegistry(uri)


@pytest.fixture
async def e2e_cache():
    """PromptCacheManager connected to real Redis with E2E cleanup."""
    url = os.environ.get("POI_PROMPT_CACHE_REDIS_URL", "redis://localhost:6379/2")
    mgr = PromptCacheManager(redis_url=url)
    await mgr.connect()
    yield mgr
    # Cleanup E2E keys
    r = await mgr.connect()
    for pattern in (
        f"prompt:{E2E_PREFIX}*",
        f"prompt:canary:{E2E_PREFIX}*",
        f"prompt:metrics:{E2E_PREFIX}*",
        f"prompt:optimization:lock:{E2E_PREFIX}*",
        f"prompt:optimization:progress:{E2E_PREFIX}*",
        f"tenant:{E2E_PREFIX}*",
    ):
        async for key in r.scan_iter(match=pattern):
            await r.delete(key)
    await mgr.close()


@pytest.fixture
def e2e_lifecycle(e2e_registry):
    """PromptLifecycleManager wired to real MLflow."""
    return PromptLifecycleManager(registry=e2e_registry, lifecycle_producer=None)


@pytest.fixture
async def e2e_run_lifecycle(e2e_cache):
    """RunLifecycleManager wired to real Redis (no DB/Kafka for speed)."""
    return RunLifecycleManager(
        prompt_cache=e2e_cache,
        lifecycle_producer=None,
        db_session_factory=None,
    )


@pytest.fixture
async def e2e_canary(e2e_cache):
    """CanaryManager wired to real Redis."""
    return CanaryManager(prompt_cache=e2e_cache)


@pytest.fixture
async def e2e_tenant_config(e2e_cache):
    """TenantConfigManager wired to real Redis."""
    return TenantConfigManager(e2e_cache)


@pytest.fixture
async def e2e_loader(e2e_cache, e2e_registry, e2e_tenant_config):
    """ZorvenPromptLoader wired to real Redis + MLflow + fresh breaker."""
    breaker = MLflowCircuitBreaker(CircuitBreakerConfig())
    return ZorvenPromptLoader(
        prompt_cache=e2e_cache,
        mlflow_registry=e2e_registry,
        tenant_config=e2e_tenant_config,
        circuit_breaker=breaker,
    )


@pytest.fixture
def e2e_prompt_name():
    """Factory returning unique E2E prompt names."""

    def _make(suffix="test"):
        short_id = uuid.uuid4().hex[:8]
        return f"{E2E_PREFIX}{suffix}_{short_id}"

    return _make


@pytest.fixture
def minimal_golden_examples():
    """5 minimal golden examples (above MIN_DATASET_SIZE=3)."""
    return [
        {
            "prompt_name": f"{E2E_PREFIX}prompt",
            "agent_code": "mra",
            "input_context": {"context.brand_name": f"Brand{i}"},
            "expected_output": f"Analysis for Brand{i}.",
            "source": "manual",
            "metadata_extra": {
                "industry": ["tech", "retail", "health"][i % 3],
                "brand_maturity": "emerging",
            },
        }
        for i in range(5)
    ]


@pytest.fixture
def insufficient_golden_examples():
    """2 examples (below MIN_DATASET_SIZE=3) for guardrail failure tests."""
    return [
        {
            "prompt_name": f"{E2E_PREFIX}prompt",
            "agent_code": "mra",
            "input_context": {"context.brand_name": f"Brand{i}"},
            "expected_output": f"Output {i}.",
            "source": "manual",
            "metadata_extra": {"industry": "tech"},
        }
        for i in range(2)
    ]
