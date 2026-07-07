"""FastAPI application for the Creative Generation Agent service.

Registers 12 executable skills (SKL-CGA-01 through SKL-CGA-14, minus 06)
with Kafka integration, Nano Banana 2 image generation, and full
WF1 + WF2 + CAA context loading.
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
from app.services.cga_analyzer import CGAAnalyzer
from app.services.cga_executor import CGAExecutor
from app.services.context_loader import CGAContextLoader
from app.services.gcs_client import GCSClient
from app.services.image_gen_client import create_image_gen_client
from app.prompts.loader import AgentPromptClient
from app.prompts.invalidator import PromptCacheInvalidator

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and teardown all dependencies."""
    setup_logging()
    logger.info(
        "Starting Creative Generation Agent service on port %d", settings.PORT
    )

    # 1. Redis
    redis_manager = RedisManager()
    await redis_manager.connect()

    # 2. Kafka producers
    trace_producer = TraceProducer(settings.KAFKA_BOOTSTRAP_SERVERS)
    await trace_producer.start()
    audit_producer = AuditProducer(settings.KAFKA_BOOTSTRAP_SERVERS)
    await audit_producer.start()

    # 3. Anthropic client (lazy — for copy generation)
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

    # 4. Nano Banana 2 image generation client
    image_gen_client = create_image_gen_client()

    # 5. GCS client
    gcs_client = GCSClient(
        project_id=settings.GCS_PROJECT_ID,
        bucket_name=settings.GCS_BUCKET_NAME,
        credentials_json=settings.GCS_CREDENTIALS_JSON,
        credentials_path=settings.GCS_CREDENTIALS_PATH,
    )

    # 6. Event emitter
    event_emitter = EventEmitter(audit_producer)

    # 7. Context loader
    context_loader = CGAContextLoader()

    # 8. Analyzer
    from app.services.anthropic_client import AnthropicClient

    llm_wrapper = AnthropicClient(anthropic_client) if anthropic_client else None
    analyzer = CGAAnalyzer(
        anthropic_client=llm_wrapper,
        image_gen_client=image_gen_client,
        event_emitter=event_emitter,
        gcs_client=gcs_client,
        redis_manager=redis_manager,
    )

    # 9. Executor
    executor = CGAExecutor(
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

    logger.info("Creative Generation Agent service ready")


    # Prompt loader + cache invalidator (ZorvenPromptLoader integration)
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

    yield

    # Teardown
    await cache_invalidator.stop()
    await prompt_loader.stop()
    await trace_producer.stop()
    await audit_producer.stop()
    await redis_manager.close()
    logger.info("Creative Generation Agent service stopped")


app = FastAPI(
    title="Creative Generation Agent",
    description="WF3 Agent 3.2 — AI image generation + ad copy for Meta Ads campaigns",
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
