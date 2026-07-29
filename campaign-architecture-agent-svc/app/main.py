"""FastAPI application for the Campaign Architecture Agent service.

Registers 12 executable skills (SKL-CAA-01 through SKL-CAA-12)
with Kafka integration, Tavily web research, optional Odoo CRM
and RAG Intelligence Loop for Meta campaign blueprint generation.
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
from app.services.caa_analyzer import CAAAnalyzer
from app.services.caa_executor import CAAExecutor
from app.services.context_loader import CAAContextLoader
from app.services.gcs_client import GCSClient
from app.services.tavily_client import TavilyClient
from app.prompts.loader import AgentPromptClient
from app.prompts.invalidator import PromptCacheInvalidator

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and teardown all dependencies."""
    setup_logging()
    logger.info(
        "Starting Campaign Architecture Agent service on port %d",
        settings.PORT,
    )

    # 1. Redis
    redis_manager = RedisManager()
    await redis_manager.connect()

    # 2. Kafka producers
    trace_producer = TraceProducer(settings.KAFKA_BOOTSTRAP_SERVERS)
    await trace_producer.start()
    audit_producer = AuditProducer(settings.KAFKA_BOOTSTRAP_SERVERS)
    await audit_producer.start()

    # 3. Anthropic client (lazy)
    anthropic_client = None
    api_key = settings.ANTHROPIC_API_KEY
    if api_key:
        try:
            import anthropic

            anthropic_client = anthropic.AsyncAnthropic(api_key=api_key)
            masked = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "***"
            logger.info(
                "Anthropic client initialized (model: %s, key: %s, len: %d)",
                settings.ANTHROPIC_MODEL,
                masked,
                len(api_key),
            )
        except Exception as exc:
            logger.warning("Anthropic client init failed: %s", exc)
    else:
        logger.warning(
            "Set CAA_ANTHROPIC_API_KEY on the Cloud Run service for live results"
        )

    # 4. GCS client
    gcs_client = GCSClient(
        project_id=settings.GCS_PROJECT_ID,
        bucket_name=settings.GCS_BUCKET_NAME,
        credentials_json=settings.GCS_CREDENTIALS_JSON,
        credentials_path=settings.GCS_CREDENTIALS_PATH,
    )

    # 5. Tavily client (web research)
    tavily_client = TavilyClient(
        api_key=settings.TAVILY_API_KEY,
        redis_manager=redis_manager,
        benchmark_cache_ttl=settings.TAVILY_BENCHMARK_CACHE_TTL,
        competitor_cache_ttl=settings.TAVILY_COMPETITOR_CACHE_TTL,
    )

    # 6. Event emitter
    event_emitter = EventEmitter(audit_producer)

    # 7. Context loader
    context_loader = CAAContextLoader()

    # 8. Prompt loader + cache invalidator (ZorvenPromptLoader integration)
    prompt_loader = AgentPromptClient(
        redis_url=settings.PROMPT_CACHE_REDIS_URL,
        mlflow_uri=settings.MLFLOW_TRACKING_URI,
        fallback_only=settings.PROMPT_FALLBACK_ONLY,
    )
    await prompt_loader.start()

    cache_invalidator = PromptCacheInvalidator(
        bootstrap_servers=getattr(settings, "KAFKA_BOOTSTRAP_SERVERS", ""),
        prompt_loader=prompt_loader,
    )
    await cache_invalidator.start()

    # 9. Analyzer
    from app.services.anthropic_client import AnthropicClient

    llm_wrapper = AnthropicClient(anthropic_client) if anthropic_client else None
    analyzer = CAAAnalyzer(
        anthropic_client=llm_wrapper,
        event_emitter=event_emitter,
        gcs_client=gcs_client,
        redis_manager=redis_manager,
        tavily_client=tavily_client,
        prompt_loader=prompt_loader,
    )

    # 10. Executor
    executor = CAAExecutor(
        analyzer=analyzer,
        redis_manager=redis_manager,
        trace_producer=trace_producer,
        audit_producer=audit_producer,
        event_emitter=event_emitter,
        context_loader=context_loader,
        gcs_client=gcs_client,
    )

    # Store in app state for route access
    app.state.executor = executor
    app.state.redis_manager = redis_manager

    logger.info("Campaign Architecture Agent service ready")

    yield

    # Teardown
    await cache_invalidator.stop()
    await prompt_loader.stop()
    await trace_producer.stop()
    await audit_producer.stop()
    await redis_manager.close()
    logger.info("Campaign Architecture Agent service stopped")


app = FastAPI(
    title="Campaign Architecture Agent",
    description=(
        "WF3 Agent 3.1 — Meta Ads campaign architecture"
        " (blueprint, funnel mapping, audience targeting)"
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
