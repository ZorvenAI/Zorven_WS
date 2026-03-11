"""
Market Research Agent Service — FastAPI application entry point.

Provides structured market research capabilities including market sizing
(TAM/SAM/SOM), competitive landscape analysis, industry trend tracking,
and economic indicator lookups.
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
from app.logic.guardrails import InputGuardrail, OutputGuardrail
from app.logic.market_researcher import MarketResearcher
from app.messaging.kafka_producer import AuditProducer, TraceProducer
from app.services.api_clients import GNewsClient, TavilySearchClient, WorldBankClient
from app.services.mra_executor import MRAExecutor

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown hooks."""
    setup_logging()
    logger.info(
        "Market Research Agent starting on %s:%d",
        settings.HOST,
        settings.PORT,
    )

    # Initialize Redis manager
    redis_manager = RedisManager(settings.REDIS_URL)

    # Initialize API clients
    tavily_client = TavilySearchClient(settings.TAVILY_API_KEY, redis_manager)
    world_bank_client = WorldBankClient(settings.WORLD_BANK_BASE_URL, redis_manager)
    news_client = GNewsClient(settings.GNEWS_API_KEY, redis_manager)

    # Initialize Kafka producers
    trace_producer = TraceProducer(settings.KAFKA_BOOTSTRAP_SERVERS)
    await trace_producer.start()
    audit_producer = AuditProducer(settings.KAFKA_BOOTSTRAP_SERVERS)
    await audit_producer.start()

    # Initialize market researcher
    researcher = MarketResearcher(
        tavily_client=tavily_client,
        world_bank_client=world_bank_client,
        news_client=news_client,
        anthropic_api_key=settings.ANTHROPIC_API_KEY,
        model=settings.LLM_MODEL,
        temperature=settings.LLM_TEMPERATURE,
        max_tokens=settings.LLM_MAX_TOKENS,
    )

    # Initialize executor
    executor = MRAExecutor(
        researcher=researcher,
        redis_manager=redis_manager,
        trace_producer=trace_producer,
        audit_producer=audit_producer,
        input_guard=InputGuardrail(),
        output_guard=OutputGuardrail(),
    )
    routes.executor = executor

    if settings.ANTHROPIC_API_KEY:
        logger.info("Anthropic API key configured — live LLM mode")
    else:
        logger.warning("No Anthropic API key — running in stub mode")

    if settings.TAVILY_API_KEY:
        logger.info("Tavily API key configured — live web search mode")
    else:
        logger.warning("No Tavily API key — web search disabled")

    yield

    # Shutdown
    await executor.close()
    routes.executor = None
    logger.info("Market Research Agent shut down")


app = FastAPI(
    title="Market Research Agent Service",
    description="Market research, sizing, and competitive analysis agent",
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
