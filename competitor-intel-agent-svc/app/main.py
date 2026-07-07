"""
Competitor Intelligence Agent Service - FastAPI application entry point.

Provides structured competitive intelligence capabilities including competitor
discovery, profiling (website, social, reviews, pricing), SWOT analysis,
positioning gap analysis, and competitive benchmarking. Implements 12 executable
skills (SKL-CIA-01 through SKL-CIA-12) with 3-layer guardrails, RBAC, and
circuit breakers.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes
from app.api.routes import router
from app.cache.redis_manager import RedisManager
from app.circuit_breaker.breaker import create_circuit_breakers
from app.core.config import settings
from app.core.logging_config import setup_logging
from app.events.catalog import EventEmitter
from app.logic.competitor_analyzer import CompetitorAnalyzer
from app.logic.guardrails import (
    InputGuardrails,
    OutputGuardrails,
    PlanToolGuardrails,
)
from app.messaging.kafka_producer import AuditProducer, TraceProducer
from app.rbac.engine import RBACEngine
from app.services.api_clients import TavilySearchClient, WebScraperClient
from app.services.cia_executor import CIAExecutor
from app.skills.registry import SkillRegistry
from app.prompts.loader import AgentPromptClient
from app.prompts.invalidator import PromptCacheInvalidator

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown hooks."""
    setup_logging()
    logger.info(
        "Competitor Intelligence Agent starting on %s:%d",
        settings.HOST,
        settings.PORT,
    )

    # Initialize Redis manager
    redis_manager = RedisManager(
        settings.REDIS_URL,
        result_cache_ttl=settings.RESULT_CACHE_TTL,
        profile_cache_ttl=settings.COMPETITOR_PROFILE_TTL,
    )

    # Initialize API clients
    tavily_client = TavilySearchClient(
        settings.TAVILY_API_KEY, redis_manager,
        mcp_server_url=settings.TAVILY_MCP_SERVER_URL,
    )
    web_scraper = WebScraperClient(max_pages_per_domain=settings.MAX_PAGES_PER_DOMAIN)

    # Initialize Kafka producers
    trace_producer = TraceProducer(settings.KAFKA_BOOTSTRAP_SERVERS)
    await trace_producer.start()
    audit_producer = AuditProducer(settings.KAFKA_BOOTSTRAP_SERVERS)
    await audit_producer.start()

    # Initialize Anthropic client (lazy - only if API key present)
    anthropic_client = None
    if settings.ANTHROPIC_API_KEY:
        try:
            import anthropic

            anthropic_client = anthropic.AsyncAnthropic(
                api_key=settings.ANTHROPIC_API_KEY,
                timeout=120.0,
            )
            logger.info("Anthropic client initialized - live LLM mode")
        except Exception as exc:
            logger.warning("Failed to initialize Anthropic client: %s", exc)
    else:
        logger.warning("No Anthropic API key - running in stub mode")

    # Initialize circuit breakers
    circuit_breakers = create_circuit_breakers(settings)

    # Initialize skill registry — register read skills (SKL-CIA-01 through 07)
    skill_registry = SkillRegistry()

    from app.skills.competitor_discovery_search import CompetitorDiscoverySearch
    from app.skills.competitor_website_profiler import CompetitorWebsiteProfiler
    from app.skills.customer_review_aggregator import CustomerReviewAggregator
    from app.skills.market_share_estimator import MarketShareEstimator
    from app.skills.pricing_strategy_extractor import PricingStrategyExtractor
    from app.skills.rag_context_retrieval import RAGContextRetrieval
    from app.skills.social_media_analyzer import SocialMediaAnalyzer

    skill_registry.register(CompetitorDiscoverySearch(tavily_client))
    skill_registry.register(CompetitorWebsiteProfiler(web_scraper))
    skill_registry.register(SocialMediaAnalyzer(tavily_client))
    skill_registry.register(CustomerReviewAggregator(tavily_client))
    skill_registry.register(PricingStrategyExtractor(web_scraper, tavily_client))
    skill_registry.register(MarketShareEstimator(tavily_client))
    skill_registry.register(
        RAGContextRetrieval(settings.RAG_SERVICE_URL, settings.RAG_ENABLED)
    )

    # Register analysis skills (SKL-CIA-08 through 10) — require Anthropic client
    from app.skills.swot_analysis_generator import SWOTAnalysisGenerator
    from app.skills.positioning_gap_analyzer import PositioningGapAnalyzer
    from app.skills.competitive_benchmarking_synthesizer import (
        CompetitiveBenchmarkingSynthesizer,
    )

    skill_registry.register(
        SWOTAnalysisGenerator(
            anthropic_client, settings.LLM_MODEL,
            settings.LLM_TEMPERATURE, settings.LLM_MAX_TOKENS,
        )
    )
    skill_registry.register(
        PositioningGapAnalyzer(
            anthropic_client, settings.LLM_MODEL,
            settings.LLM_TEMPERATURE, settings.LLM_MAX_TOKENS,
        )
    )
    skill_registry.register(
        CompetitiveBenchmarkingSynthesizer(
            anthropic_client, settings.LLM_MODEL,
            settings.LLM_TEMPERATURE, settings.LLM_MAX_TOKENS,
        )
    )

    # Register write + escalation skills (SKL-CIA-11, 12)
    from app.skills.competitor_report_persister import CompetitorReportPersister
    from app.skills.human_escalation import HumanEscalation

    skill_registry.register(
        CompetitorReportPersister(
            gcs_enabled=settings.GCS_ENABLED,
            rag_enabled=settings.RAG_ENABLED,
            rag_service_url=settings.RAG_SERVICE_URL,
        )
    )
    skill_registry.register(HumanEscalation(audit_producer))

    # Initialize RBAC engine
    rbac_engine = RBACEngine(enabled=settings.RBAC_ENABLED)

    # Initialize event emitter
    event_emitter = EventEmitter(audit_producer)

    # Initialize 3-layer guardrails
    input_guardrails = InputGuardrails(redis_manager, settings)
    plan_guardrails = PlanToolGuardrails(rbac_engine, settings)
    output_guardrails = OutputGuardrails(settings)

    # Initialize competitor analyzer (skill-based PAOR engine)
    analyzer = CompetitorAnalyzer(
        skill_registry=skill_registry,
        rbac_engine=rbac_engine,
        circuit_breakers=circuit_breakers,
        input_guardrails=input_guardrails,
        plan_guardrails=plan_guardrails,
        output_guardrails=output_guardrails,
        event_emitter=event_emitter,
        anthropic_client=anthropic_client,
        model=settings.LLM_MODEL,
        temperature=settings.LLM_TEMPERATURE,
        max_tokens=settings.LLM_MAX_TOKENS,
    )

    # Initialize executor (thin wrapper - guardrails handled by analyzer)
    executor = CIAExecutor(
        analyzer=analyzer,
        redis_manager=redis_manager,
        trace_producer=trace_producer,
        audit_producer=audit_producer,
    )
    routes.executor = executor

    # Initialize Kafka consumer for scheduled scans (if enabled)
    scan_consumer = None
    if settings.KAFKA_CONSUMERS_ENABLED:
        from app.messaging.kafka_consumer import ScheduledScanConsumer

        scan_consumer = ScheduledScanConsumer(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            consumer_group=settings.KAFKA_CONSUMER_GROUP,
            executor=executor,
            redis_manager=redis_manager,
        )
        await scan_consumer.start()
        logger.info("Scheduled scan consumer started")

    if settings.TAVILY_API_KEY:
        logger.info("Tavily API key configured - live web search mode")
    else:
        logger.warning("No Tavily API key - web search disabled")

    logger.info(
        "CIA initialized: %d skills, RBAC=%s, %d circuit breakers, consumer=%s",
        len(skill_registry.get_all_skills()),
        settings.RBAC_ENABLED,
        len(circuit_breakers),
        scan_consumer is not None,
    )

    # Prompt loader + cache invalidator (ZorvenPromptLoader integration)
    prompt_loader = AgentPromptClient(
        redis_url=settings.PROMPT_CACHE_REDIS_URL,
        mlflow_uri=settings.MLFLOW_TRACKING_URI,
    )
    await prompt_loader.start()

    cache_invalidator = PromptCacheInvalidator(
        bootstrap_servers=getattr(settings, "KAFKA_BOOTSTRAP_SERVERS", ""),
        prompt_loader=prompt_loader,
    )
    await cache_invalidator.start()

    yield

    # Shutdown
    await cache_invalidator.stop()
    await prompt_loader.stop()
    if scan_consumer:
        await scan_consumer.stop()
    await executor.close()
    if anthropic_client:
        try:
            await anthropic_client.close()
        except Exception:
            pass
    routes.executor = None
    logger.info("Competitor Intelligence Agent shut down")


app = FastAPI(
    title="Competitor Intelligence Agent Service",
    description=(
        "Competitor profiling, SWOT analysis, positioning gaps, "
        "and competitive benchmarking with 12 skills"
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in settings.CORS_ORIGINS.split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
