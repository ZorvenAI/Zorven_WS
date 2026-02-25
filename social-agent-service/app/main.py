"""FastAPI application entry point with lifespan hooks."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import google.generativeai as genai
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes
from app.cache.redis_manager import RedisManager
from app.core.config import settings
from app.core.logging_config import setup_logging
from app.logic.asset_resolver import AssetResolver
from app.logic.platform_adapter import PlatformAdapter
from app.messaging.kafka_consumer import ContentPublishedConsumer
from app.messaging.kafka_producer import SocialAuditProducer, TraceProducer
from app.services.core_api_client import CoreApiClient
from app.logic.action_resolver import ActionResolver
from app.services.mcp_client import McpClient
from app.services.social_executor import SocialExecutor

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown hooks."""
    setup_logging()
    logger.info("Social Agent starting up ...")

    # Redis
    redis_manager = RedisManager(settings.REDIS_URL)
    logger.info("Redis manager initialised: %s", settings.REDIS_URL)

    # Gemini (optional)
    gemini_model = None
    if settings.GOOGLE_API_KEY:
        genai.configure(api_key=settings.GOOGLE_API_KEY)
        gemini_model = genai.GenerativeModel(settings.GEMINI_MODEL)
        logger.info("Gemini configured: %s", settings.GEMINI_MODEL)
    else:
        logger.warning("SOCIAL_GOOGLE_API_KEY not set — running in stub mode")

    # Core API client
    core_api_client = CoreApiClient(
        base_url=settings.CORE_API_URL,
        service_token=settings.CORE_API_TOKEN,
    )

    # Kafka producers
    trace_producer = TraceProducer(settings.KAFKA_BOOTSTRAP_SERVERS)
    audit_producer = SocialAuditProducer(
        settings.KAFKA_BOOTSTRAP_SERVERS,
        topic=settings.SOCIAL_AUDIT_TOPIC,
    )

    # Logic components
    platform_adapter = PlatformAdapter(gemini_model=gemini_model)
    asset_resolver = AssetResolver(core_api_client)
    action_resolver = ActionResolver(gemini_model=gemini_model)

    # MCP client (optional)
    mcp_client = None
    if settings.MCP_SERVER_URL:
        mcp_client = McpClient(settings.MCP_SERVER_URL)
        logger.info("MCP client configured: %s", settings.MCP_SERVER_URL)
    else:
        logger.info("MCP client disabled (no MCP_SERVER_URL)")

    # Executor
    executor = SocialExecutor(
        platform_adapter=platform_adapter,
        asset_resolver=asset_resolver,
        core_api_client=core_api_client,
        redis_manager=redis_manager,
        trace_producer=trace_producer,
        audit_producer=audit_producer,
        action_resolver=action_resolver,
        mcp_client=mcp_client,
    )
    routes.executor = executor

    # Kafka consumer (background task)
    consumer = ContentPublishedConsumer(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        topic=settings.CONTENT_PUBLISHED_TOPIC,
        executor=executor,
    )
    consumer_task: asyncio.Task[None] | None = None
    if settings.KAFKA_BOOTSTRAP_SERVERS:
        consumer_task = asyncio.create_task(consumer.start())
        logger.info(
            "Kafka consumer started for topic: %s",
            settings.CONTENT_PUBLISHED_TOPIC,
        )
    else:
        logger.info("Kafka disabled (no bootstrap servers configured)")

    logger.info("Social Agent ready on port %s", settings.PORT)
    yield

    # Shutdown
    if consumer_task is not None:
        consumer.stop()
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass

    await executor.close()
    routes.executor = None
    logger.info("Social Agent shut down")


app = FastAPI(
    title="Social Agent Service",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes.router)
