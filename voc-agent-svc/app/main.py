"""FastAPI application for the Voice of Customer Agent service.

Registers 14 executable skills (SKL-VoCA-01 through SKL-VoCA-14)
with 3-layer guardrails, RBAC, circuit breakers, and Kafka integration.
"""

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
from app.logic.guardrails import ThreeLayerGuardrails
from app.logic.voc_analyzer import VoCAAnalyzer
from app.messaging.kafka_producer import AlertProducer, AuditProducer, TraceProducer
from app.rbac.engine import RBACEngine
from app.services.voc_executor import VoCAExecutor
from app.services.api_clients import TavilySearchClient, WebScraperClient
from app.skills.registry import SkillRegistry

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and teardown all dependencies."""
    setup_logging()
    logger.info(
        "Starting Voice of Customer Agent service on port %d", settings.PORT
    )

    # 1. Redis
    redis_manager = RedisManager()
    await redis_manager.connect()

    # 2. API clients
    tavily_client = TavilySearchClient(
        mcp_server_url=settings.TAVILY_MCP_SERVER_URL
    )
    web_scraper = WebScraperClient()
    await web_scraper.start()

    # 3. Kafka producers
    trace_producer = TraceProducer(settings.KAFKA_BOOTSTRAP_SERVERS)
    await trace_producer.start()
    audit_producer = AuditProducer(settings.KAFKA_BOOTSTRAP_SERVERS)
    await audit_producer.start()
    alert_producer = AlertProducer(settings.KAFKA_BOOTSTRAP_SERVERS)
    await alert_producer.start()

    # 4. Anthropic client (lazy)
    anthropic_client = None
    if settings.ANTHROPIC_API_KEY:
        try:
            import anthropic

            anthropic_client = anthropic.AsyncAnthropic(
                api_key=settings.ANTHROPIC_API_KEY
            )
            logger.info(
                "Anthropic client initialized (model=%s)",
                settings.LLM_MODEL,
            )
        except Exception as exc:
            logger.warning("Failed to initialize Anthropic client: %s", exc)

    # 5. Circuit breakers
    breakers = create_breakers(settings)

    # 6. Skill registry — register all 14 skills
    skill_registry = SkillRegistry()

    # Phase 1: External research skills (SKL-VoCA-05..08) — parallel
    from app.skills.external_review_miner import ExternalReviewMiner
    from app.skills.social_feedback_collector import SocialFeedbackCollector
    from app.skills.forum_discussion_miner import ForumDiscussionMiner
    from app.skills.rag_context_retrieval import RAGContextRetrieval

    skill_registry.register(ExternalReviewMiner(tavily_client, web_scraper))
    skill_registry.register(SocialFeedbackCollector(tavily_client))
    skill_registry.register(ForumDiscussionMiner(tavily_client, web_scraper))
    skill_registry.register(
        RAGContextRetrieval(
            settings.RAG_SERVICE_URL, bool(settings.RAG_SERVICE_URL)
        )
    )

    # Odoo skills (SKL-VoCA-01..04) — conditionally registered
    odoo_client = None
    if settings.ODOO_ENABLED:
        from app.services.odoo_rpc_client import OdooRPCClient
        from app.skills.odoo_helpdesk_extractor import OdooHelpdeskExtractor
        from app.skills.odoo_survey_extractor import OdooSurveyExtractor
        from app.skills.odoo_chatter_extractor import OdooChatterExtractor
        from app.skills.odoo_customer_segment_linker import (
            OdooCustomerSegmentLinker,
        )

        odoo_client = OdooRPCClient(
            url=settings.ODOO_URL,
            db=settings.ODOO_DB,
            username=settings.ODOO_USERNAME,
            password=settings.ODOO_PASSWORD,
        )
        skill_registry.register(
            OdooHelpdeskExtractor(odoo_client, redis_manager)
        )
        skill_registry.register(
            OdooSurveyExtractor(odoo_client, redis_manager)
        )
        skill_registry.register(
            OdooChatterExtractor(odoo_client, redis_manager)
        )
        skill_registry.register(OdooCustomerSegmentLinker())
        logger.info("Odoo skills registered (01-04)")

    # Phase 2: Analysis skills (SKL-VoCA-09..12) — sequential
    from app.skills.sentiment_analyzer import SentimentAnalyzer
    from app.skills.theme_cluster_builder import ThemeClusterBuilder
    from app.skills.nps_trend_analyzer import NPSTrendAnalyzer
    from app.skills.voc_strategy_bridge import VoCStrategyBridge

    skill_registry.register(
        SentimentAnalyzer(
            anthropic_client,
            settings.LLM_MODEL,
            settings.LLM_TEMPERATURE,
            settings.LLM_MAX_TOKENS,
        )
    )
    skill_registry.register(
        ThemeClusterBuilder(
            anthropic_client,
            settings.LLM_MODEL,
            settings.LLM_TEMPERATURE,
            settings.LLM_MAX_TOKENS,
        )
    )
    skill_registry.register(
        NPSTrendAnalyzer(
            anthropic_client,
            settings.LLM_MODEL,
            settings.LLM_TEMPERATURE,
            settings.LLM_MAX_TOKENS,
        )
    )
    skill_registry.register(
        VoCStrategyBridge(
            anthropic_client,
            settings.LLM_MODEL,
            settings.LLM_TEMPERATURE,
            settings.LLM_MAX_TOKENS,
            settings,
        )
    )

    # Phase 3: Write + Escalation skills (SKL-VoCA-13..14)
    from app.skills.voc_report_persister import VoCReportPersister
    from app.skills.human_escalation import HumanEscalation

    # Feedback registry
    from app.registry.feedback_registry import FeedbackRegistry

    event_emitter = EventEmitter(audit_producer=audit_producer)
    feedback_registry = FeedbackRegistry(
        redis_client=redis_manager._redis,
        event_emitter=event_emitter,
    )

    skill_registry.register(
        VoCReportPersister(
            gcs_enabled=bool(settings.GCS_CREDENTIALS_JSON),
            rag_enabled=bool(settings.RAG_SERVICE_URL),
            rag_service_url=settings.RAG_SERVICE_URL,
            feedback_registry=feedback_registry,
            alert_producer=alert_producer,
        )
    )
    skill_registry.register(HumanEscalation(audit_producer))

    logger.info(
        "Skill registry initialized (%d skills)",
        len(skill_registry.skill_ids()),
    )

    # 7. RBAC engine
    rbac_engine = RBACEngine()

    # 8. Guardrails
    guardrails = ThreeLayerGuardrails(
        redis_manager=redis_manager,
        rbac_engine=rbac_engine,
        anthropic_client=anthropic_client,
    )

    # 9. VoCAAnalyzer (PAOR engine)
    analyzer = VoCAAnalyzer(
        skill_registry=skill_registry,
        guardrails=guardrails,
        circuit_breakers=breakers,
        event_emitter=event_emitter,
        anthropic_client=anthropic_client,
    )

    # 10. VoCAExecutor
    executor = VoCAExecutor(
        analyzer=analyzer,
        redis_manager=redis_manager,
        trace_producer=trace_producer,
        audit_producer=audit_producer,
        event_emitter=event_emitter,
    )

    # Inject executor into routes
    routes.executor = executor

    # Initialize Kafka consumer for scheduled scans (if enabled)
    scan_consumer = None
    if settings.KAFKA_CONSUMERS_ENABLED:
        from app.messaging.kafka_consumer import ScheduledScanConsumer

        scan_consumer = ScheduledScanConsumer(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            consumer_group="voice-of-customer-agent-group",
            executor=executor,
            redis_manager=redis_manager,
        )
        await scan_consumer.start()
        logger.info("Scheduled scan consumer started")

    logger.info(
        "VoCA initialized: %d skills, Odoo=%s, consumer=%s",
        len(skill_registry.skill_ids()),
        settings.ODOO_ENABLED,
        scan_consumer is not None,
    )

    yield

    # Shutdown
    logger.info("Shutting down Voice of Customer Agent service")
    if scan_consumer:
        await scan_consumer.stop()
    await executor.close()
    await alert_producer.stop()
    await web_scraper.close()


app = FastAPI(
    title="Voice of Customer Agent",
    description=(
        "AI-powered VoC analysis: sentiment, themes, NPS, "
        "strategy bridge (Agent 1.5)"
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
