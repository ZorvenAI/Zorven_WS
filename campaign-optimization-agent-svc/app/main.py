"""FastAPI application for the Campaign Optimization Agent service.

WF3 Agent 3.4 -- Continuously optimizes live Meta Ads campaigns
via Celery Beat scheduled ticks. The platform's ONLY scheduled worker.

Registers 13 executable skills (SKL-COA-01 through SKL-COA-13).
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
from app.messaging.kafka_producer import (
    AuditProducer,
    EventProducer,
    TraceProducer,
)
from app.services.anthropic_client import AnthropicClient
from app.services.approval_handler import ApprovalHandler
from app.services.autonomous_executor import AutonomousExecutor
from app.services.budget_analyzer import BudgetAnalyzer
from app.services.callback_client import CallbackClient
from app.services.campaign_discovery import CampaignDiscovery
from app.services.fatigue_detector import FatigueDetector
from app.services.meta_insights_client import MetaInsightsClient
from app.services.meta_management_client import MetaManagementClient
from app.services.optimization_persister import OptimizationPersister
from app.services.optimization_verifier import OptimizationVerifier
from app.services.performance_analyzer import PerformanceAnalyzer
from app.services.recommendation_generator import RecommendationGenerator
from app.services.reporter import Reporter
from app.prompts.loader import AgentPromptClient
from app.prompts.invalidator import PromptCacheInvalidator

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and teardown all dependencies."""
    setup_logging()
    logger.info(
        "Starting Campaign Optimization Agent on port %d "
        "(sandbox=%s)",
        settings.PORT,
        settings.META_ADS_SANDBOX_MODE,
    )

    # 1. Redis (DB 24)
    redis_manager = RedisManager()
    await redis_manager.connect()

    # 2. Kafka producers
    trace_producer = TraceProducer(settings.KAFKA_BOOTSTRAP_SERVERS)
    await trace_producer.start()
    audit_producer = AuditProducer(settings.KAFKA_BOOTSTRAP_SERVERS)
    await audit_producer.start()
    event_producer = EventProducer(settings.KAFKA_BOOTSTRAP_SERVERS)
    await event_producer.start()

    # 3. Anthropic client (Claude Sonnet 4 for analysis narratives)
    anthropic_client = None
    llm_wrapper = None
    if settings.ANTHROPIC_API_KEY:
        try:
            import anthropic

            anthropic_client = anthropic.AsyncAnthropic(
                api_key=settings.ANTHROPIC_API_KEY
            )
            llm_wrapper = AnthropicClient(
                anthropic_client, model=settings.ANTHROPIC_MODEL
            )
            logger.info(
                "Anthropic client initialized (model: %s)",
                settings.ANTHROPIC_MODEL,
            )
        except Exception as exc:
            logger.warning("Anthropic client init failed: %s", exc)

    # 4. Event emitter
    event_emitter = EventEmitter(audit_producer)

    # 5. Meta clients
    meta_insights = MetaInsightsClient(
        api_version=settings.META_API_VERSION,
        sandbox_mode=settings.META_ADS_SANDBOX_MODE,
    )
    meta_management = MetaManagementClient(
        api_version=settings.META_API_VERSION,
        sandbox_mode=settings.META_ADS_SANDBOX_MODE,
    )

    # 6. Service instances
    callback_client = CallbackClient()
    campaign_discovery = CampaignDiscovery(redis_manager=redis_manager)
    verifier = OptimizationVerifier()
    executor = AutonomousExecutor(
        meta_client=meta_management,
        verifier=verifier,
        event_emitter=event_emitter,
        redis_manager=redis_manager,
    )
    approval_handler = ApprovalHandler(
        redis_manager=redis_manager,
        event_emitter=event_emitter,
        autonomous_executor=executor,
    )
    persister = OptimizationPersister(
        callback_client=callback_client,
        redis_manager=redis_manager,
    )
    analyzer = PerformanceAnalyzer(llm_client=llm_wrapper)
    fatigue_detector = FatigueDetector()
    budget_analyzer = BudgetAnalyzer()
    rec_generator = RecommendationGenerator(llm_client=llm_wrapper)
    reporter = Reporter(llm_client=llm_wrapper)

    # Store in app state for route access
    app.state.redis_manager = redis_manager
    app.state.approval_handler = approval_handler
    app.state.event_emitter = event_emitter
    app.state.meta_insights = meta_insights
    app.state.meta_management = meta_management
    app.state.executor = executor
    app.state.analyzer = analyzer
    app.state.reporter = reporter
    app.state.callback_client = callback_client

    logger.info("Campaign Optimization Agent service ready")


    # Prompt loader + cache invalidator (ZorvenPromptLoader integration)
    prompt_loader = AgentPromptClient(
        critical_agent=True,
        redis_url=settings.PROMPT_CACHE_REDIS_URL,
        mlflow_uri=settings.MLFLOW_TRACKING_URI,
    )
    await prompt_loader.start()

    cache_invalidator = PromptCacheInvalidator(
        bootstrap_servers=getattr(settings, "KAFKA_BOOTSTRAP_SERVERS", ""),
        prompt_loader=prompt_loader,
    )
    await cache_invalidator.start()

    yield

    # Teardown
    await trace_producer.stop()
    await audit_producer.stop()
    await event_producer.stop()
    await redis_manager.close()
    logger.info("Campaign Optimization Agent service stopped")


app = FastAPI(
    title="Campaign Optimization Agent",
    description=(
        "WF3 Agent 3.4 -- Continuously optimizes live Meta Ads "
        "campaigns via scheduled optimization ticks"
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
origins = [
    o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(routes.router)
