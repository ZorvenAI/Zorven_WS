"""FastAPI application for the Naming & Tagline Agent service.

Registers 14 executable skills (SKL-NTA-01 through SKL-NTA-14)
with Kafka integration and WF1 + BPA + BPV + BAA + Company context loading.
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
from app.services.nta_analyzer import NTAAnalyzer
from app.services.nta_executor import NTAExecutor
from app.services.context_loader import NTAContextLoader
from app.prompts.loader import AgentPromptClient
from app.prompts.invalidator import PromptCacheInvalidator

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and teardown all dependencies."""
    setup_logging()
    logger.info("Starting Naming & Tagline Agent service on port %d", settings.PORT)

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
            logger.info(
                "Anthropic client initialized (key=%s...%s, length=%d, model=%s)",
                api_key[:4],
                api_key[-4:],
                len(api_key),
                settings.ANTHROPIC_MODEL,
            )
        except Exception as exc:
            logger.warning("Anthropic client init failed: %s", exc)
    else:
        logger.warning(
            "Set NTA_ANTHROPIC_API_KEY on the Cloud Run service for live results"
        )

    # 4. Event emitter
    event_emitter = EventEmitter(audit_producer)

    # 5. Context loader
    context_loader = NTAContextLoader()

    # 6. Prompt loader (ZorvenPromptLoader integration) — init before analyzer
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

    # 7. Analyzer
    from app.services.anthropic_client import AnthropicClient

    llm_wrapper = AnthropicClient(anthropic_client) if anthropic_client else None
    analyzer = NTAAnalyzer(
        anthropic_client=llm_wrapper,
        event_emitter=event_emitter,
        prompt_loader=prompt_loader,
    )

    # 8. Executor
    executor = NTAExecutor(
        analyzer=analyzer,
        redis_manager=redis_manager,
        trace_producer=trace_producer,
        audit_producer=audit_producer,
        event_emitter=event_emitter,
        context_loader=context_loader,
    )

    # Store in app state for route access
    app.state.executor = executor
    app.state.redis_manager = redis_manager
    app.state.prompt_loader = prompt_loader

    logger.info("Naming & Tagline Agent service ready")

    yield

    # Teardown
    await cache_invalidator.stop()
    await prompt_loader.stop()
    await trace_producer.stop()
    await audit_producer.stop()
    await redis_manager.close()
    logger.info("Naming & Tagline Agent service stopped")


app = FastAPI(
    title="Naming & Tagline Agent",
    description="WF2 Agent 2.4 — Brand naming & tagline generation with availability checking",
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
