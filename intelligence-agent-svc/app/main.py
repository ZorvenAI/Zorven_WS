"""
Intelligence Agent Service — FastAPI application entry point.

ISO 10668 brand valuation and analytical intelligence agent.
Performs Royalty Relief NPV calculations, Brand Strength Index scoring,
competitive gap analysis, and theme extraction for pipeline orchestration.
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
from app.logic.analysis.competitive_gap import CompetitiveGapAnalyzer
from app.logic.analysis.theme_analyzer import ThemeAnalyzer
from app.logic.iso_engine.bsi_calculator import BSICalculator
from app.logic.iso_engine.proxy_engine import ProxyEngine
from app.logic.iso_engine.royalty_relief import RoyaltyReliefEngine
from app.prompts.loader import AgentPromptClient
from app.services.intelligence_executor import IntelligenceExecutor
from app.services.rag_adapter import RAGAdapter
from app.services.storage_service import StorageService

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown hooks."""
    setup_logging()
    logger.info(
        "Intelligence Agent starting on %s:%d",
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

    # Initialize storage service (GCS)
    storage_service: StorageService | None = None
    if settings.GCS_PROJECT_ID:
        storage_service = StorageService(
            project_id=settings.GCS_PROJECT_ID,
            bucket_name=settings.GCS_BUCKET_NAME,
            credentials_path=settings.GCS_CREDENTIALS_PATH,
        )
        logger.info("GCS storage configured for project: %s", settings.GCS_PROJECT_ID)
    else:
        logger.info("No GCS config — storage service in stub mode")

    # Initialize RAG adapter (Vertex AI)
    rag_adapter: RAGAdapter | None = None
    if settings.RAG_PROJECT_ID:
        rag_adapter = RAGAdapter(
            project_id=settings.RAG_PROJECT_ID,
            location=settings.RAG_LOCATION,
        )
        logger.info("RAG adapter configured for project: %s", settings.RAG_PROJECT_ID)
    else:
        logger.info("No RAG config — RAG adapter in stub mode")

    # Initialize Gemini client (optional)
    gemini_client = None
    if settings.GEMINI_API_KEY:
        try:
            import google.generativeai as genai

            genai.configure(api_key=settings.GEMINI_API_KEY)
            gemini_client = genai
            logger.info("Gemini AI configured (model: %s)", settings.GEMINI_MODEL)
        except Exception as exc:
            logger.warning("Failed to initialize Gemini: %s", exc)
    else:
        logger.info("No Gemini API key — running in rule-based mode only")

    # Initialize logic engines
    proxy_engine = ProxyEngine()
    royalty_engine = RoyaltyReliefEngine()
    bsi_calculator = BSICalculator(proxy_engine=proxy_engine)
    gap_analyzer = CompetitiveGapAnalyzer(prompt_loader=prompt_loader)
    theme_analyzer = ThemeAnalyzer()

    # Initialize executor with all dependencies
    executor = IntelligenceExecutor(
        royalty_engine=royalty_engine,
        bsi_calculator=bsi_calculator,
        proxy_engine=proxy_engine,
        gap_analyzer=gap_analyzer,
        theme_analyzer=theme_analyzer,
        storage_service=storage_service,
        rag_adapter=rag_adapter,
        redis_manager=redis_manager,
        gemini_client=gemini_client,
        prompt_loader=prompt_loader,
    )
    routes.executor = executor

    yield

    # Shutdown
    await executor.close()
    await prompt_loader.stop()
    routes.executor = None
    logger.info("Intelligence Agent shut down")


app = FastAPI(
    title="Intelligence Agent Service",
    description="ISO 10668 brand valuation and analytical intelligence agent",
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
