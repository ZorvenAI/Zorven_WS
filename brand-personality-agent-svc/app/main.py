"""FastAPI application for the Brand Personality & Values Agent service.

Registers 12 executable skills (SKL-BPV-01 through SKL-BPV-12)
with Kafka integration and WF1 + BPA + BAA + Company context loading.
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
from app.services.bpv_analyzer import BPVAnalyzer
from app.services.bpv_executor import BPVExecutor
from app.services.context_loader import BPVContextLoader

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and teardown all dependencies."""
    setup_logging()
    logger.info("Starting Brand Personality Agent service on port %d", settings.PORT)

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
            logger.info("Anthropic client initialized (model: %s)", settings.ANTHROPIC_MODEL)
        except Exception as exc:
            logger.warning("Anthropic client init failed: %s", exc)

    # 4. Event emitter
    event_emitter = EventEmitter(audit_producer)

    # 5. Context loader
    context_loader = BPVContextLoader()

    # 6. Analyzer
    from app.services.anthropic_client import AnthropicClient

    llm_wrapper = AnthropicClient(anthropic_client) if anthropic_client else None
    analyzer = BPVAnalyzer(
        anthropic_client=llm_wrapper,
        event_emitter=event_emitter,
    )

    # 7. Executor
    executor = BPVExecutor(
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

    logger.info("Brand Personality Agent service ready")

    yield

    # Teardown
    await trace_producer.stop()
    await audit_producer.stop()
    await event_producer.stop()
    await redis_manager.close()
    logger.info("Brand Personality Agent service stopped")


app = FastAPI(
    title="Brand Personality & Values Agent",
    description="WF2 Agent 2.3 — Brand personality design using Aaker 5D + Jungian archetypes",
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
