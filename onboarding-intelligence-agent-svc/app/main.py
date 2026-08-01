"""FastAPI application, lifespan and dependency wiring.

Configuration is resolved at import time. A missing required variable raises a
Pydantic validation error here — before the server binds a port — so a
misconfigured deploy fails loudly at rollout rather than quietly at the first
meeting (A-05 AC-2).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from app.api.routes import router
from app.cache.redis_manager import RedisManager
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.telemetry import configure_telemetry
from app.messaging.producer import KafkaProducer

settings = get_settings()
configure_logging(settings.LOG_LEVEL)
configure_telemetry(settings.OTEL_EXPORTER_ENDPOINT)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open connections on startup, close them on shutdown.

    Startup does not abort when a dependency is down. The health probe is the
    place where that is reported — a service that refuses to start cannot tell
    anyone *why* it is unhealthy, and Cloud Run would restart-loop it.
    """
    app.state.settings = settings
    app.state.redis = RedisManager(settings)
    app.state.kafka = KafkaProducer(settings)

    await app.state.redis.connect()
    try:
        await app.state.kafka.start()
    except Exception as exc:  # noqa: BLE001 — reported via /health
        logger.warning("kafka_start_failed", error=str(exc))

    logger.info(
        "service_started",
        service="onboarding-intelligence-agent",
        port=settings.PORT,
        redis_db=settings.REDIS_DB,
        kafka_configured=settings.kafka_enabled,
    )

    yield

    await app.state.kafka.stop()
    await app.state.redis.close()
    logger.info("service_stopped")


app = FastAPI(
    title="Onboarding Intelligence Agent",
    description=(
        "Turns a recorded onboarding conversation, the documents shown during "
        "it, and the operator's prepared questions into a complete, "
        "provenance-tracked brand profile."
    ),
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(router)
