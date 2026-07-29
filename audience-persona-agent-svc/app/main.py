"""FastAPI application for the Audience Persona Agent service.

Registers 14 executable skills (SKL-APA-01 through SKL-APA-12 + 05b + 05c)
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
from app.logic.persona_analyzer import PersonaAnalyzer
from app.messaging.kafka_producer import AuditProducer, TraceProducer
from app.rbac.engine import RBACEngine
from app.services.apa_executor import APAExecutor
from app.services.api_clients import TavilySearchClient, WebScraperClient
from app.skills.registry import SkillRegistry
from app.prompts.loader import AgentPromptClient
from app.prompts.invalidator import PromptCacheInvalidator

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and teardown all dependencies."""
    setup_logging()
    logger.info("Starting Audience Persona Agent service on port %d", settings.PORT)

    # 1. Redis
    redis_manager = RedisManager()
    await redis_manager.connect()

    # 2. API clients
    tavily_client = TavilySearchClient(mcp_server_url=settings.TAVILY_MCP_SERVER_URL)
    web_scraper = WebScraperClient()
    await web_scraper.start()

    # 3. Kafka producers
    trace_producer = TraceProducer(settings.KAFKA_BOOTSTRAP_SERVERS)
    await trace_producer.start()
    audit_producer = AuditProducer(settings.KAFKA_BOOTSTRAP_SERVERS)
    await audit_producer.start()

    # 4. Anthropic client (lazy)
    anthropic_client = None
    if settings.ANTHROPIC_API_KEY:
        try:
            import anthropic

            anthropic_client = anthropic.AsyncAnthropic(
                api_key=settings.ANTHROPIC_API_KEY
            )
            key = settings.ANTHROPIC_API_KEY
            masked = f"{key[:4]}...{key[-4:]}" if len(key) > 8 else "***"
            logger.info(
                "Anthropic client initialized (key=%s, length=%d, model=%s)",
                masked,
                len(key),
                settings.LLM_MODEL,
            )
        except Exception as exc:
            logger.warning("Failed to initialize Anthropic client: %s", exc)
    else:
        logger.error(
            "ANTHROPIC_API_KEY is not set — LLM skills will run in stub mode. "
            "Set APA_ANTHROPIC_API_KEY on the Cloud Run service"
        )

    # 5. Prompt loader + cache invalidator (ZorvenPromptLoader integration)
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

    # 6. Circuit breakers
    breakers = create_breakers(settings)

    # 7. Skill registry — register all 14 skills
    skill_registry = SkillRegistry()

    # Phase 1: Research skills (SKL-APA-01 through 06) — parallel execution
    from app.skills.audience_landscape_research import AudienceLandscapeResearch
    from app.skills.buyer_role_extractor import BuyerRoleExtractor
    from app.skills.forum_community_miner import ForumCommunityMiner
    from app.skills.rag_context_retrieval import RAGContextRetrieval
    from app.skills.review_needs_miner import ReviewNeedsMiner
    from app.skills.social_listening_analyzer import SocialListeningAnalyzer

    skill_registry.register(AudienceLandscapeResearch(tavily_client))
    skill_registry.register(ForumCommunityMiner(tavily_client, web_scraper))
    skill_registry.register(SocialListeningAnalyzer(tavily_client))
    skill_registry.register(BuyerRoleExtractor(tavily_client))
    skill_registry.register(ReviewNeedsMiner(tavily_client))
    skill_registry.register(
        RAGContextRetrieval(settings.RAG_SERVICE_URL, bool(settings.RAG_SERVICE_URL))
    )

    # Odoo skills (SKL-APA-05b, 05c) — conditionally registered
    odoo_client = None
    if settings.ODOO_ENABLED:
        from app.services.odoo_rpc_client import OdooRPCClient
        from app.skills.odoo_crm_customer_extractor import OdooCRMCustomerExtractor
        from app.skills.odoo_survey_data_extractor import OdooSurveyDataExtractor

        odoo_client = OdooRPCClient(
            url=settings.ODOO_URL,
            db=settings.ODOO_DB,
            username=settings.ODOO_USERNAME,
            password=settings.ODOO_PASSWORD,
        )
        skill_registry.register(OdooSurveyDataExtractor(odoo_client, redis_manager))
        skill_registry.register(OdooCRMCustomerExtractor(odoo_client, redis_manager))
        logger.info("Odoo skills registered (05b, 05c)")

    # Phase 2: Analysis skills (SKL-APA-07 through 10) — sequential execution
    from app.skills.buying_journey_mapper import BuyingJourneyMapper
    from app.skills.demographic_profile_builder import DemographicProfileBuilder
    from app.skills.persona_synthesizer import PersonaSynthesizer
    from app.skills.psychographic_behavioral_profiler import (
        PsychographicBehavioralProfiler,
    )

    skill_registry.register(
        DemographicProfileBuilder(
            anthropic_client,
            settings.LLM_MODEL,
            settings.LLM_MAX_TOKENS,
            prompt_loader=prompt_loader,
        )
    )
    skill_registry.register(
        PsychographicBehavioralProfiler(
            anthropic_client,
            settings.LLM_MODEL,
            settings.LLM_MAX_TOKENS,
            prompt_loader=prompt_loader,
        )
    )
    skill_registry.register(
        PersonaSynthesizer(
            anthropic_client,
            settings.LLM_MODEL,
            settings.LLM_MAX_TOKENS,
            prompt_loader=prompt_loader,
        )
    )
    skill_registry.register(
        BuyingJourneyMapper(
            anthropic_client,
            settings.LLM_MODEL,
            settings.LLM_MAX_TOKENS,
            prompt_loader=prompt_loader,
        )
    )

    # Phase 3: Write + Escalation skills (SKL-APA-11, 12)
    from app.skills.human_escalation import HumanEscalation
    from app.skills.persona_report_persister import PersonaReportPersister

    # Persona registry
    from app.registry.persona_registry import PersonaRegistry

    event_emitter = EventEmitter(audit_producer=audit_producer)
    persona_registry = PersonaRegistry(
        redis_client=redis_manager._redis,
        event_emitter=event_emitter,
    )

    skill_registry.register(
        PersonaReportPersister(
            gcs_enabled=bool(settings.GCS_CREDENTIALS_JSON),
            rag_enabled=bool(settings.RAG_SERVICE_URL),
            rag_service_url=settings.RAG_SERVICE_URL,
            persona_registry=persona_registry,
        )
    )
    skill_registry.register(HumanEscalation(audit_producer))

    logger.info(
        "Skill registry initialized (%d skills)", len(skill_registry.skill_ids())
    )

    # 7. RBAC engine
    rbac_engine = RBACEngine()

    # 9. Guardrails
    guardrails = ThreeLayerGuardrails(
        redis_manager=redis_manager,
        rbac_engine=rbac_engine,
        anthropic_client=anthropic_client,
    )

    # 10. PersonaAnalyzer (PAOR engine)
    analyzer = PersonaAnalyzer(
        skill_registry=skill_registry,
        guardrails=guardrails,
        circuit_breakers=breakers,
        event_emitter=event_emitter,
        anthropic_client=anthropic_client,
        prompt_loader=prompt_loader,
    )

    # 11. APAExecutor
    executor = APAExecutor(
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
            consumer_group="audience-persona-agent-group",
            executor=executor,
            redis_manager=redis_manager,
        )
        await scan_consumer.start()
        logger.info("Scheduled scan consumer started")

    logger.info(
        "APA initialized: %d skills, Odoo=%s, consumer=%s",
        len(skill_registry.skill_ids()),
        settings.ODOO_ENABLED,
        scan_consumer is not None,
    )

    yield

    # Shutdown
    logger.info("Shutting down Audience Persona Agent service")
    await cache_invalidator.stop()
    await prompt_loader.stop()
    if scan_consumer:
        await scan_consumer.stop()
    await executor.close()
    await web_scraper.close()


app = FastAPI(
    title="Audience Persona Agent",
    description="AI-powered buyer persona research and generation (Agent 1.3)",
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
