"""FastAPI application for the Ad Publishing Agent service.

WF3 Agent 3.3 — Publishes approved creative packages as live Meta Ads
with mandatory human approval gate. SAFETY-CRITICAL: the only agent
that spends real money.

Registers 12 executable skills (SKL-APA33-01 through SKL-APA33-12).
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes
from app.core.config import settings
from app.core.logging_config import setup_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and teardown all dependencies."""
    setup_logging()
    logger.info(
        "Starting Ad Publishing Agent service on port %d "
        "(sandbox=%s)",
        settings.PORT,
        settings.META_ADS_SANDBOX_MODE,
    )

    # Dependencies will be initialized here in later phases:
    # 1. Redis (DB 23)
    # 2. Kafka producers (trace, audit, event)
    # 3. Anthropic client (Claude Sonnet 4 for targeting translation)
    # 4. Meta API client (facebook-business SDK)
    # 5. GCS client (read creative package images)
    # 6. Event emitter
    # 7. Context loader
    # 8. Approval manager
    # 9. Analyzer (7-phase publishing engine)
    # 10. Executor

    logger.info("Ad Publishing Agent service ready")

    yield

    logger.info("Ad Publishing Agent service stopped")


app = FastAPI(
    title="Ad Publishing Agent",
    description=(
        "WF3 Agent 3.3 — Publishes approved creative packages as "
        "live Meta Ads with mandatory human approval gate"
    ),
    version="1.0.0",
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

# Routes
app.include_router(routes.router)
