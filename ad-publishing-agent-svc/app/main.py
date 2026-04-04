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
from app.cache.redis_manager import RedisManager
from app.core.config import settings
from app.core.logging_config import setup_logging
from app.messaging.event_emitter import EventEmitter
from app.messaging.kafka_producer import AuditProducer, TraceProducer
from app.services.adpub_analyzer import AdPubAnalyzer
from app.services.adpub_executor import AdPubExecutor
from app.services.approval_manager import ApprovalManager
from app.services.context_loader import AdPubContextLoader
from app.services.meta_api_client import MetaApiClient
from app.services.targeting_translator import TargetingTranslator

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

    # 1. Redis (DB 23)
    redis_manager = RedisManager()
    await redis_manager.connect()

    # 2. Kafka producers
    trace_producer = TraceProducer(settings.KAFKA_BOOTSTRAP_SERVERS)
    await trace_producer.start()
    audit_producer = AuditProducer(settings.KAFKA_BOOTSTRAP_SERVERS)
    await audit_producer.start()

    # 3. Anthropic client (Claude Sonnet 4 for targeting translation)
    anthropic_client = None
    if settings.ANTHROPIC_API_KEY:
        try:
            import anthropic

            anthropic_client = anthropic.AsyncAnthropic(
                api_key=settings.ANTHROPIC_API_KEY
            )
            logger.info(
                "Anthropic client initialized (model: %s)",
                settings.ANTHROPIC_MODEL,
            )
        except Exception as exc:
            logger.warning("Anthropic client init failed: %s", exc)

    # 4. LLM wrapper + targeting translator
    from app.services.anthropic_client import AnthropicClient

    llm_wrapper = AnthropicClient(anthropic_client) if anthropic_client else None
    targeting_translator = TargetingTranslator(llm_client=llm_wrapper)

    # 5. Meta API client
    meta_client = MetaApiClient(
        api_version=settings.META_API_VERSION,
        sandbox_mode=settings.META_ADS_SANDBOX_MODE,
    )

    # 6. Event emitter
    event_emitter = EventEmitter(audit_producer)

    # 7. Context loader
    context_loader = AdPubContextLoader()

    # 8. Approval manager
    approval_manager = ApprovalManager(
        redis_manager=redis_manager,
        expiry_seconds=settings.APPROVAL_EXPIRY_SECONDS,
    )

    # 9. Analyzer (7-phase publishing engine)
    analyzer = AdPubAnalyzer(
        meta_client=meta_client,
        targeting_translator=targeting_translator,
        event_emitter=event_emitter,
    )

    # 10. Executor
    executor = AdPubExecutor(
        analyzer=analyzer,
        approval_manager=approval_manager,
        context_loader=context_loader,
        redis_manager=redis_manager,
        trace_producer=trace_producer,
        audit_producer=audit_producer,
        event_emitter=event_emitter,
        daily_spend_cap_usd=settings.DAILY_SPEND_CAP_USD,
        min_audience_size=settings.MIN_AUDIENCE_SIZE,
        max_campaign_budget_usd=settings.MAX_CAMPAIGN_BUDGET_USD,
    )

    # Store in app state for route access
    app.state.executor = executor
    app.state.approval_manager = approval_manager
    app.state.redis_manager = redis_manager

    logger.info("Ad Publishing Agent service ready")

    yield

    # Teardown
    await trace_producer.stop()
    await audit_producer.stop()
    await redis_manager.close()
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
