"""
Pipeline Orchestrator Service — FastAPI application entry point.

Converts JSON manifests into stateful LangGraphs and executes them
as multi-agent pipelines with real-time progress reporting.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes as api_routes
from app.api.routes import router
from app.core.config import settings
from app.core.logging_config import setup_logging
from app.core.redis_client import close_redis
from app.messaging.kafka_consumer import TriggerConsumer
from app.messaging.kafka_producer import TraceProducer
from app.skills.loader import load_all_skills
from app.skills.registry import SkillRegistry
from app.skills.router import SkillRouter

logger = logging.getLogger(__name__)

# Module-level Kafka instances (optional — graceful if broker unavailable)
trace_producer = TraceProducer(settings.KAFKA_BOOTSTRAP_SERVERS)
trigger_consumer = TriggerConsumer(settings.KAFKA_BOOTSTRAP_SERVERS)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown hooks."""
    setup_logging()
    logger.info(
        "Pipeline Orchestrator starting on %s:%d",
        settings.HOST,
        settings.PORT,
    )

    # Load runtime skills (fail-open — service works without skills)
    skills = load_all_skills()
    skill_registry = SkillRegistry(skills)
    api_routes.skill_router = SkillRouter(skill_registry)
    logger.info("Skill system initialized: %d skill(s) loaded", len(skills))

    # Start Kafka producer + consumer (optional — non-fatal if unavailable)
    await trace_producer.start()
    await trigger_consumer.start()

    # Start Kafka consumer loop in background if connected
    consumer_task = None
    executor = None
    if trigger_consumer.is_connected:
        from app.services.job_executor import JobExecutor

        executor = JobExecutor()
        consumer_task = asyncio.create_task(trigger_consumer.consume(executor))
        logger.info("Kafka consume loop started in background")

    yield

    # Shutdown
    if consumer_task is not None:
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass

    if executor is not None:
        await executor.close()

    await trigger_consumer.stop()
    await trace_producer.stop()
    await close_redis()
    api_routes.skill_router = None
    logger.info("Pipeline Orchestrator shut down")


app = FastAPI(
    title="Pipeline Orchestrator Service",
    description="Pipeline-as-Code runtime engine using LangGraph",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
