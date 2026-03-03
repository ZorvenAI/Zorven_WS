"""FastAPI application — Brand Equity Calculator Service.

ISO 20671:2019 brand equity evaluation powered by Claude AI (Anthropic).
Public-facing, no authentication required.
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.api import routes
from app.cache.redis_manager import RedisManager
from app.core.config import settings
from app.core.logging_config import setup_logging
from app.services.brand_equity_executor import BrandEquityExecutor

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialize dependencies on startup, clean up on shutdown."""
    setup_logging()
    logger.info(
        "Brand Equity Calculator starting on %s:%d", settings.HOST, settings.PORT
    )

    # Redis (fail-open — service works without it, just no caching)
    redis_manager = RedisManager(settings.REDIS_URL)

    # Anthropic Claude client
    claude_client = None
    if settings.ANTHROPIC_API_KEY:
        try:
            import anthropic

            claude_client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
            logger.info(
                "Anthropic Claude configured (model: %s)", settings.CLAUDE_MODEL
            )
        except Exception as exc:
            logger.error("Failed to initialize Anthropic client: %s", exc)
    else:
        logger.warning(
            "No BRAND_EQUITY_ANTHROPIC_API_KEY set — "
            "/v1/calculate will return 503 until configured"
        )

    # Executor
    executor = BrandEquityExecutor(
        redis_manager=redis_manager,
        claude_client=claude_client,
    )
    routes.executor = executor

    yield

    await redis_manager.close()
    routes.executor = None
    logger.info("Brand Equity Calculator shut down")


app = FastAPI(
    title="Brand Equity Calculator Service",
    description="ISO 20671:2019 brand equity evaluation powered by Claude AI",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow frontend origins
origins = [
    origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
