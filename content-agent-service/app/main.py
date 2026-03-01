"""
Content Agent Service — FastAPI application entry point.

SEO/AEO/GEO-compliant blog authoring agent.
Receives research data from discovery-agent-svc via the pipeline orchestrator,
fetches brand persona from core-api, and produces polished Markdown blog posts
with structured metadata.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes
from app.api.routes import router
from app.cache.redis_manager import RedisManager
from app.core.config import settings
from app.core.logging_config import setup_logging
from app.logic.aeo_formatter import AEOFormatter
from app.logic.blog_author import BlogAuthor
from app.logic.geo_synthesizer import GEOSynthesizer
from app.logic.seo_optimizer import SEOOptimizer
from app.messaging.kafka_producer import ContentPublishedProducer, TraceProducer
from app.services.content_executor import ContentExecutor
from app.services.core_api_client import CoreApiClient
from app.services.gcs_client import GCSClient

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown hooks."""
    setup_logging()
    logger.info(
        "Content Agent starting on %s:%d",
        settings.HOST,
        settings.PORT,
    )

    # Initialize Redis manager
    redis_manager = RedisManager(settings.REDIS_URL)

    # Initialize Gemini client (optional)
    gemini_model = None
    if settings.GOOGLE_API_KEY:
        try:
            import google.generativeai as genai

            genai.configure(api_key=settings.GOOGLE_API_KEY)
            gemini_model = genai.GenerativeModel(settings.GEMINI_MODEL)
            logger.info("Gemini AI configured (model: %s)", settings.GEMINI_MODEL)
        except Exception as exc:
            logger.warning("Failed to initialize Gemini: %s", exc)
    else:
        logger.info("No Google API key — running in stub mode")

    # Initialize GCS client
    gcs_client = GCSClient(
        project_id=settings.GCS_PROJECT_ID,
        bucket_name=settings.GCS_BUCKET_NAME,
        credentials_path=settings.GCS_CREDENTIALS_PATH,
        credentials_json=settings.GCS_CREDENTIALS_JSON,
    )

    # Initialize Core API client
    core_api_client = CoreApiClient(
        base_url=settings.CORE_API_URL,
        service_token=settings.CORE_API_TOKEN,
    )

    # Initialize Kafka producers
    trace_producer = TraceProducer(settings.KAFKA_BOOTSTRAP_SERVERS)
    await trace_producer.start()

    published_producer = ContentPublishedProducer(settings.KAFKA_BOOTSTRAP_SERVERS)
    await published_producer.start()

    # Initialize logic components
    seo_optimizer = SEOOptimizer(gemini_model=gemini_model)
    aeo_formatter = AEOFormatter(gemini_model=gemini_model)
    geo_synthesizer = GEOSynthesizer()
    blog_author = BlogAuthor(gemini_model=gemini_model)

    # Build executor
    executor = ContentExecutor(
        seo_optimizer=seo_optimizer,
        aeo_formatter=aeo_formatter,
        geo_synthesizer=geo_synthesizer,
        blog_author=blog_author,
        core_api_client=core_api_client,
        gcs_client=gcs_client,
        redis_manager=redis_manager,
        trace_producer=trace_producer,
        published_producer=published_producer,
    )
    routes.executor = executor

    yield

    # Shutdown
    await executor.close()
    routes.executor = None
    logger.info("Content Agent shut down")


app = FastAPI(
    title="Content Agent Service",
    description="SEO/AEO/GEO-compliant blog authoring agent",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
