"""FastAPI application for the Brand Positioning Agent service.

Registers 12 executable skills (SKL-BPA-01 through SKL-BPA-12)
with Kafka integration and WF1 context loading.
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
from app.messaging.kafka_producer import AuditProducer, EventProducer, TraceProducer
from app.services.bpa_analyzer import BPAAnalyzer
from app.services.bpa_executor import BPAExecutor
from app.services.wf1_loader import WF1ContextLoader
from app.prompts.loader import AgentPromptClient

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and teardown all dependencies."""
    setup_logging()
    logger.info("Starting Brand Positioning Agent service on port %d", settings.PORT)

    # 1. Redis
    redis_manager = RedisManager()
    await redis_manager.connect()

    # 2. Kafka producers
    trace_producer = TraceProducer(settings.KAFKA_BOOTSTRAP_SERVERS)
    await trace_producer.start()
    audit_producer = AuditProducer(settings.KAFKA_BOOTSTRAP_SERVERS)
    await audit_producer.start()
    event_producer = EventProducer(settings.KAFKA_BOOTSTRAP_SERVERS)
    await event_producer.start()

    # 3. Anthropic client (lazy)
    anthropic_client = None
    if settings.ANTHROPIC_API_KEY:
        try:
            import anthropic

            anthropic_client = anthropic.AsyncAnthropic(
                api_key=settings.ANTHROPIC_API_KEY
            )
            logger.info(
                "Anthropic client initialized (model=%s)",
                settings.ANTHROPIC_MODEL,
            )
        except Exception as exc:
            logger.warning("Failed to initialize Anthropic client: %s", exc)

    # 4. Anthropic wrapper
    from app.services.anthropic_client import AnthropicClient

    llm_client = AnthropicClient(
        client=anthropic_client,
        model=settings.ANTHROPIC_MODEL,
        temperature=settings.ANTHROPIC_TEMPERATURE,
        max_tokens=settings.ANTHROPIC_MAX_TOKENS,
    )

    # 5. Event emitter
    event_emitter = EventEmitter(audit_producer=audit_producer)

    # 6. WF1 context loader
    wf1_loader = WF1ContextLoader(
        backend_url=settings.BACKEND_URL,
        service_token=settings.BACKEND_SERVICE_TOKEN,
    )

    # 7. BPA Analyzer (PAOR engine)
    analyzer = BPAAnalyzer(
        anthropic_client=llm_client,
        event_emitter=event_emitter,
    )

    # 8. BPA Executor
    executor = BPAExecutor(
        analyzer=analyzer,
        redis_manager=redis_manager,
        trace_producer=trace_producer,
        audit_producer=audit_producer,
        event_emitter=event_emitter,
        wf1_loader=wf1_loader,
    )

    # Inject executor into routes
    routes.executor = executor

    logger.info(
        "BPA initialized: Anthropic=%s, WF1 backend=%s",
        bool(anthropic_client),
        settings.BACKEND_URL,
    )


    # Prompt loader (ZorvenPromptLoader integration)
    prompt_loader = AgentPromptClient(
        redis_url=settings.PROMPT_CACHE_REDIS_URL,
        mlflow_uri=settings.MLFLOW_TRACKING_URI,
    )
    await prompt_loader.start()
    routes.prompt_loader = prompt_loader

    yield

    # Shutdown
    await prompt_loader.stop()
    logger.info("Shutting down Brand Positioning Agent service")
    await executor.close()
    await event_producer.stop()


app = FastAPI(
    title="Brand Positioning Agent",
    description=(
        "AI-powered brand positioning: framework-agnostic statements, "
        "value proposition canvas, perceptual maps, differentiation "
        "(WF2 Agent 2.1)"
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

app.include_router(routes.router)
