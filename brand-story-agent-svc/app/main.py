"""FastAPI application for the Brand Story Agent service.

Registers 14 executable skills (SKL-BSA-01 through SKL-BSA-14)
with Kafka integration and WF1 + BPA + BPV + NTA + BAA + Company context loading.
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
from app.services.bsa_analyzer import BSAAnalyzer
from app.services.bsa_executor import BSAExecutor
from app.services.context_loader import BSAContextLoader
from app.services.gcs_client import GCSClient
from app.prompts.loader import AgentPromptClient
from app.prompts.invalidator import PromptCacheInvalidator

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and teardown all dependencies."""
    setup_logging()
    logger.info("Starting Brand Story Agent service on port %d", settings.PORT)

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
    if settings.ANTHROPIC_API_KEY:
        try:
            import anthropic

            anthropic_client = anthropic.AsyncAnthropic(
                api_key=settings.ANTHROPIC_API_KEY
            )
            logger.info(
                "Anthropic client initialized (model: %s)", settings.ANTHROPIC_MODEL
            )
        except Exception as exc:
            logger.warning("Anthropic client init failed: %s", exc)

    # 4. GCS client
    gcs_client = GCSClient(
        project_id=settings.GCS_PROJECT_ID,
        bucket_name=settings.GCS_BUCKET_NAME,
        credentials_json=settings.GCS_CREDENTIALS_JSON,
        credentials_path=settings.GCS_CREDENTIALS_PATH,
    )

    # 5. Event emitter
    event_emitter = EventEmitter(audit_producer)

    # 6. Context loader
    context_loader = BSAContextLoader()

    # 7. Analyzer
    from app.services.anthropic_client import AnthropicClient

    llm_wrapper = AnthropicClient(anthropic_client) if anthropic_client else None
    analyzer = BSAAnalyzer(
        anthropic_client=llm_wrapper,
        event_emitter=event_emitter,
        gcs_client=gcs_client,
        redis_manager=redis_manager,
    )

    # 8. Executor
    executor = BSAExecutor(
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

    logger.info("Brand Story Agent service ready")


    # Prompt loader (ZorvenPromptLoader integration)
    prompt_loader = AgentPromptClient(
        redis_url=settings.PROMPT_CACHE_REDIS_URL,
        mlflow_uri=settings.MLFLOW_TRACKING_URI,
    )
    await prompt_loader.start()

    cache_invalidator = PromptCacheInvalidator(
        bootstrap_servers=getattr(settings, "KAFKA_BOOTSTRAP_SERVERS", ""),
        prompt_loader=prompt_loader,
    )
    await cache_invalidator.start()

    app.state.prompt_loader = prompt_loader

    yield

    # Teardown
    await cache_invalidator.stop()
    await prompt_loader.stop()
    await trace_producer.stop()
    await audit_producer.stop()
    await redis_manager.close()
    logger.info("Brand Story Agent service stopped")


app = FastAPI(
    title="Brand Story Agent",
    description="WF2 Agent 2.5 — Brand story & narrative synthesis (capstone)",
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
