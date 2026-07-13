"""
RAG Uploader Agent Service — FastAPI application entry point.

Persists documents from the AI chat context into the long-term
Vertex AI RAG Store by triggering the existing Data Ingestion
pipeline via Kafka.
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
from app.logic.file_resolver import FileResolver
from app.logic.ingestion_bridge import IngestionBridge
from app.logic.smart_titler import SmartTitler
from app.messaging.kafka_producer import IngestionProducer, TraceProducer
from app.prompts.loader import AgentPromptClient
from app.services.core_api_client import CoreApiClient
from app.services.gcs_client import GCSClient
from app.services.uploader_executor import UploaderExecutor

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown hooks."""
    setup_logging()
    logger.info(
        "RAG Uploader Agent starting on %s:%d",
        settings.HOST,
        settings.PORT,
    )

    # Initialize Redis manager
    redis_manager = RedisManager(settings.REDIS_URL)

    # Initialize prompt loader
    prompt_loader = AgentPromptClient(
        redis_url=settings.PROMPT_CACHE_REDIS_URL,
        mlflow_uri=settings.MLFLOW_TRACKING_URI,
        fallback_only=settings.PROMPT_FALLBACK_ONLY,
    )
    await prompt_loader.start()

    # Initialize Gemini client (optional — for SmartTitler)
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
        logger.info("No Google API key — SmartTitler running in stub mode")

    # Initialize Kafka producers
    trace_producer = TraceProducer(settings.KAFKA_BOOTSTRAP_SERVERS)
    await trace_producer.start()

    ingestion_producer = IngestionProducer(settings.KAFKA_BOOTSTRAP_SERVERS)
    await ingestion_producer.start()

    # Initialize GCS client (for uploading content to landing zone)
    gcs_client = GCSClient(
        project_id=settings.GCS_PROJECT_ID,
        bucket_name=settings.GCS_BUCKET_NAME,
        credentials_path=settings.GCS_CREDENTIALS_PATH,
        credentials_json=settings.GCS_CREDENTIALS_JSON,
    )

    # Initialize Core API client (for BrandAsset registration)
    core_api_client = CoreApiClient(
        base_url=settings.CORE_API_URL,
        service_token=settings.CORE_API_TOKEN,
    )
    logger.info(
        "CoreApiClient configured: %s",
        settings.CORE_API_URL,
    )

    # Initialize logic components
    file_resolver = FileResolver()
    smart_titler = SmartTitler(gemini_model=gemini_model, prompt_loader=prompt_loader)
    ingestion_bridge = IngestionBridge(ingestion_producer=ingestion_producer)

    # Build executor
    executor = UploaderExecutor(
        file_resolver=file_resolver,
        smart_titler=smart_titler,
        ingestion_bridge=ingestion_bridge,
        redis_manager=redis_manager,
        trace_producer=trace_producer,
        gcs_client=gcs_client,
        core_api_client=core_api_client,
    )
    routes.executor = executor

    yield

    # Shutdown
    await prompt_loader.stop()
    await ingestion_producer.stop()
    await executor.close()
    routes.executor = None
    logger.info("RAG Uploader Agent shut down")


app = FastAPI(
    title="RAG Uploader Agent Service",
    description="Persists documents to Vertex AI RAG Store via Data Ingestion pipeline",
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
