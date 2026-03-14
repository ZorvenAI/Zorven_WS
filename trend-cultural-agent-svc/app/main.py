"""FastAPI application for the Trend & Cultural Insights Agent service."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes
from app.cache.redis_manager import RedisManager
from app.circuit_breaker.breaker import create_breakers
from app.core.config import settings
from app.core.logging_config import setup_logging
from app.events.catalog import EventEmitter
from app.logic.guardrails import GuardrailEngine
from app.logic.trend_analyzer import TrendAnalyzer
from app.messaging.kafka_producer import AlertProducer, AuditProducer, TraceProducer
from app.rbac.engine import RBACEngine
from app.registry.trend_registry import TrendRegistry
from app.services.api_clients import OdooRPCClient, TavilySearchClient, WebScraperClient
from app.services.gcs_client import GCSClient
from app.services.tcia_executor import TCIAExecutor
from app.skills.registry import SkillRegistry
from app.skills.skl_tcia_01_social_trend_scanner import SocialTrendScanner
from app.skills.skl_tcia_02_cultural_shift_monitor import CulturalShiftMonitor
from app.skills.skl_tcia_03_viral_content_analyzer import ViralContentAnalyzer
from app.skills.skl_tcia_04_generational_preference_tracker import (
    GenerationalPreferenceTracker,
)
from app.skills.skl_tcia_05_slang_language_tracker import SlangLanguageTracker
from app.skills.skl_tcia_06_rag_context_retrieval import RAGContextRetrieval
from app.skills.skl_tcia_07_cultural_relevance_scorer import CulturalRelevanceScorer
from app.skills.skl_tcia_08_trend_persona_mapper import TrendPersonaMapper
from app.skills.skl_tcia_09_opportunity_alert_generator import OpportunityAlertGenerator
from app.skills.skl_tcia_10_trend_report_synthesizer import TrendReportSynthesizer
from app.skills.skl_tcia_11_trend_report_persister import TrendReportPersister
from app.skills.skl_tcia_12_human_escalation import HumanEscalation

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown."""
    # ── STARTUP ──
    setup_logging()
    logger.info("Starting Trend & Cultural Insights Agent on port %d", settings.PORT)

    # Redis
    redis_manager = RedisManager(settings.REDIS_URL, result_ttl=settings.RESULT_CACHE_TTL)
    await redis_manager.connect()

    # API clients
    tavily_client = TavilySearchClient()
    scraper_client = WebScraperClient()
    await scraper_client.start()

    # Odoo CRM (feature-flagged)
    odoo_client = None
    if settings.ODOO_ENABLED and settings.ODOO_URL:
        odoo_client = OdooRPCClient(
            url=settings.ODOO_URL,
            db=settings.ODOO_DB,
            username=settings.ODOO_USERNAME,
            password=settings.ODOO_PASSWORD,
        )

    # GCS client
    gcs_client = GCSClient(
        project_id=settings.GCS_PROJECT_ID,
        bucket_name=settings.GCS_BUCKET_NAME,
        credentials_json=settings.GCS_CREDENTIALS_JSON,
        credentials_path=settings.GCS_CREDENTIALS_PATH,
    )

    # Kafka producers
    trace_producer = TraceProducer(settings.KAFKA_BOOTSTRAP_SERVERS)
    audit_producer = AuditProducer(settings.KAFKA_BOOTSTRAP_SERVERS)
    alert_producer = AlertProducer(settings.KAFKA_BOOTSTRAP_SERVERS)
    await trace_producer.start()
    await audit_producer.start()
    await alert_producer.start()

    # Anthropic client (lazy init)
    anthropic_client = None
    if settings.ANTHROPIC_API_KEY:
        try:
            from anthropic import AsyncAnthropic

            anthropic_client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        except Exception as exc:
            logger.warning("Failed to init Anthropic client: %s", exc)

    # Circuit breakers
    circuit_breakers = create_breakers(settings)

    # Skill registry (all 12 skills)
    skill_registry = SkillRegistry()
    skill_registry.register(
        SocialTrendScanner(
            tavily_client, scraper_client,
            circuit_breakers["tavily"], circuit_breakers["httpx"],
        )
    )
    skill_registry.register(
        CulturalShiftMonitor(tavily_client, circuit_breakers["tavily"])
    )
    skill_registry.register(
        ViralContentAnalyzer(
            tavily_client, scraper_client,
            circuit_breakers["tavily"], circuit_breakers["httpx"],
        )
    )
    skill_registry.register(
        GenerationalPreferenceTracker(tavily_client, circuit_breakers["tavily"])
    )
    skill_registry.register(
        SlangLanguageTracker(
            tavily_client, scraper_client, anthropic_client,
            circuit_breakers["tavily"], circuit_breakers["httpx"],
            circuit_breakers["llm"],
        )
    )
    skill_registry.register(
        RAGContextRetrieval(settings.RAG_SERVICE_URL, circuit_breakers["rag_store"])
    )
    skill_registry.register(
        CulturalRelevanceScorer(anthropic_client, circuit_breakers["llm"])
    )
    skill_registry.register(
        TrendPersonaMapper(anthropic_client, circuit_breakers["llm"])
    )
    skill_registry.register(
        OpportunityAlertGenerator(anthropic_client, circuit_breakers["llm"])
    )
    skill_registry.register(
        TrendReportSynthesizer(anthropic_client, circuit_breakers["llm"])
    )
    skill_registry.register(
        TrendReportPersister(
            gcs_client, settings.RAG_SERVICE_URL, redis_manager,
            alert_producer, settings.CORE_API_URL, settings.CORE_API_TOKEN,
            circuit_breakers,
        )
    )
    skill_registry.register(HumanEscalation(audit_producer))

    # Inject Odoo CRM data source into scorer if available
    if odoo_client:
        scorer = skill_registry.get_skill("SKL-TCIA-07")
        if scorer and hasattr(scorer, "set_odoo_client"):
            scorer.set_odoo_client(odoo_client, redis_manager)

    # RBAC engine
    rbac_engine = RBACEngine()

    # Event emitter
    event_emitter = EventEmitter(audit_producer=audit_producer)

    # Guardrails
    guardrails = GuardrailEngine(anthropic_client, redis_manager, event_emitter)

    # Trend registry
    trend_registry = TrendRegistry(redis_manager, event_emitter)

    # Trend analyzer (core engine)
    analyzer = TrendAnalyzer(
        skill_registry, guardrails, trend_registry, redis_manager,
        alert_producer, event_emitter, settings,
    )

    # Executor (thin wrapper)
    executor = TCIAExecutor(analyzer, redis_manager, trace_producer, audit_producer)

    # Wire to routes
    routes.executor = executor

    # Kafka consumer for scheduled scans
    kafka_consumer = None
    if settings.KAFKA_CONSUMERS_ENABLED and settings.KAFKA_BOOTSTRAP_SERVERS:
        from app.messaging.kafka_consumer import ScheduledScanConsumer

        kafka_consumer = ScheduledScanConsumer(
            settings.KAFKA_BOOTSTRAP_SERVERS, executor, redis_manager
        )
        await kafka_consumer.start()

    logger.info(
        "TCIA started: %d skills, Redis=%s, Kafka=%s, Odoo=%s",
        len(skill_registry.skill_ids()),
        "connected" if redis_manager._redis else "stub",
        "connected" if trace_producer._connected else "stub",
        "enabled" if odoo_client else "disabled",
    )

    yield

    # ── SHUTDOWN ──
    logger.info("Shutting down TCIA...")
    if kafka_consumer:
        await kafka_consumer.stop()
    await trace_producer.stop()
    await audit_producer.stop()
    await alert_producer.stop()
    await scraper_client.stop()
    if anthropic_client:
        try:
            await anthropic_client.close()
        except Exception:
            pass
    await redis_manager.close()
    routes.executor = None


app = FastAPI(
    title="Trend & Cultural Insights Agent",
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

app.include_router(router=routes.router)
