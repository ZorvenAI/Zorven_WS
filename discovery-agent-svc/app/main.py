"""
Discovery Agent Service — FastAPI application entry point.

Stateless data harvester, web researcher, and content curator.
Performs web searches via Tavily, scrapes URLs, cleans HTML to Markdown,
and returns structured findings for pipeline orchestration.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes
from app.api.routes import router
from app.cache.redis_manager import RedisManager
from app.core.config import settings
from app.core.logging_config import setup_logging
from app.messaging.kafka_producer import TraceProducer
from app.prompts.invalidator import PromptCacheInvalidator
from app.prompts.loader import AgentPromptClient
from app.scrapers.factory import ScraperFactory
from app.services.discovery_executor import DiscoveryExecutor

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown hooks."""
    setup_logging()
    logger.info(
        "Discovery Agent starting on %s:%d",
        settings.HOST,
        settings.PORT,
    )

    # Initialize Redis manager
    redis_manager = RedisManager(settings.REDIS_URL)

    # Create scraper components
    search_engine, browser_engine, data_cleaner = ScraperFactory.create(
        redis_manager=redis_manager,
    )

    # Initialize trace producer for real-time browsing events
    trace_producer = TraceProducer(settings.KAFKA_BOOTSTRAP_SERVERS)
    await trace_producer.start()

    # Initialize prompt loader (three-tier: Redis cache → MLflow → fallback)
    prompt_loader = AgentPromptClient(
        redis_url=settings.PROMPT_CACHE_REDIS_URL,
        mlflow_uri=settings.MLFLOW_TRACKING_URI,
        fallback_only=settings.PROMPT_FALLBACK_ONLY,
    )
    await prompt_loader.start()

    # Initialize prompt cache invalidator (Kafka consumer)
    prompt_invalidator = PromptCacheInvalidator(
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        prompt_loader=prompt_loader,
    )
    await prompt_invalidator.start()

    # Initialize executor
    executor = DiscoveryExecutor(
        search_engine=search_engine,
        browser_engine=browser_engine,
        data_cleaner=data_cleaner,
        redis_manager=redis_manager,
        trace_producer=trace_producer,
    )
    routes.executor = executor

    if settings.TAVILY_API_KEY:
        logger.info("Tavily API key configured — live search mode")
    else:
        logger.warning("No Tavily API key — running in stub mode")

    yield

    # Shutdown
    await prompt_invalidator.stop()
    await prompt_loader.stop()
    await executor.close()
    routes.executor = None
    logger.info("Discovery Agent shut down")


app = FastAPI(
    title="Discovery Agent Service",
    description="Web research and content curation agent",
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
