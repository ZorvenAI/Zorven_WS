"""FastAPI application for the Intelligence Loop Agent (WF3.5)."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes
from app.cache.redis_manager import RedisManager
from app.core.config import settings
from app.core.logging_config import setup_logging
from app.messaging.kafka_consumer import IlaKafkaConsumer
from app.messaging.kafka_producer import AuditProducer, EventProducer
from app.services.django_client import DjangoClient
from app.services.extractor import IntelligenceExtractor
from app.prompts.loader import AgentPromptClient
from app.prompts.invalidator import PromptCacheInvalidator

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info(
        "Starting Intelligence Loop Agent on port %d (mode default=%s)",
        settings.PORT,
        settings.DEFAULT_MODE,
    )

    redis_manager = RedisManager()
    await redis_manager.connect()

    audit = AuditProducer(settings.KAFKA_BOOTSTRAP_SERVERS, settings.AUDIT_TOPIC)
    events = EventProducer(settings.KAFKA_BOOTSTRAP_SERVERS, settings.EVENTS_TOPIC)
    await audit.start()
    await events.start()

    app.state.redis_manager = redis_manager
    app.state.audit_producer = audit
    app.state.event_producer = events

    # Prompt loader + cache invalidator (ZorvenPromptLoader integration)
    # Initialized before IntelligenceExtractor so it can be injected.
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

    django_client = DjangoClient()
    extractor = IntelligenceExtractor(
        django_client=django_client,
        prompt_loader=prompt_loader,
    )

    consumer = IlaKafkaConsumer(extractor=extractor)
    await consumer.start()

    app.state.django_client = django_client
    app.state.extractor = extractor
    app.state.kafka_consumer = consumer

    logger.info("Intelligence Loop Agent ready")

    yield

    await cache_invalidator.stop()
    await prompt_loader.stop()
    await consumer.stop()
    await audit.stop()
    await events.stop()
    await redis_manager.close()
    logger.info("Intelligence Loop Agent stopped")


app = FastAPI(
    title="Intelligence Loop Agent",
    description="WF3.5 — closes the feedback loop across WF1+WF2+WF3.",
    version="0.1.0",
    lifespan=lifespan,
)

origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes.router)
