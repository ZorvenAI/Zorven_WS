"""FastAPI application for the Brand Architecture Agent service.

Registers 12 executable skills (SKL-BAA-01 through SKL-BAA-12)
with Kafka integration and WF1 + BPA + Company context loading.
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
from app.services.baa_analyzer import BAAAnalyzer
from app.services.baa_executor import BAAExecutor
from app.services.context_loader import BAAContextLoader

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and teardown all dependencies."""
    setup_logging()
    logger.info("Starting Brand Architecture Agent service on port %d", settings.PORT)

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

    # 6. Context loader (WF1 + BPA + Company)
    context_loader = BAAContextLoader(
        backend_url=settings.BACKEND_URL,
        service_token=settings.BACKEND_SERVICE_TOKEN,
    )

    # 7. BAA Analyzer (PAOR engine)
    analyzer = BAAAnalyzer(
        anthropic_client=llm_client,
        event_emitter=event_emitter,
    )

    # 8. BAA Executor
    executor = BAAExecutor(
        analyzer=analyzer,
        redis_manager=redis_manager,
        trace_producer=trace_producer,
        audit_producer=audit_producer,
        event_emitter=event_emitter,
        context_loader=context_loader,
    )

    # Inject executor into routes
    routes.executor = executor

    logger.info(
        "BAA initialized: Anthropic=%s, backend=%s",
        bool(anthropic_client),
        settings.BACKEND_URL,
    )

    yield

    # Shutdown
    logger.info("Shutting down Brand Architecture Agent service")
    await executor.close()
    await event_producer.stop()


app = FastAPI(
    title="Brand Architecture Agent",
    description=(
        "AI-powered brand architecture: model recommendation, hierarchy tree, "
        "naming conventions, portfolio growth path (WF2 Agent 2.2)"
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
