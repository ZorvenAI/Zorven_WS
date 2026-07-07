"""
Market Research Agent Service — FastAPI application entry point.

Provides structured market research capabilities including market sizing
(TAM/SAM/SOM), competitive landscape analysis, industry trend tracking,
and economic indicator lookups. Implements 8 executable skills (SKL-MRA-01
through SKL-MRA-08) with 3-layer guardrails, RBAC, and circuit breakers.
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
from app.logic.guardrails import (
    InputGuardrails,
    OutputGuardrails,
    PlanToolGuardrails,
)
from app.logic.market_researcher import MarketResearcher
from app.messaging.kafka_producer import AuditProducer, TraceProducer
from app.rbac.engine import RBACEngine
from app.services.api_clients import GNewsClient, TavilySearchClient, WorldBankClient
from app.services.mra_executor import MRAExecutor
from app.skills.economic_indicator_lookup import EconomicIndicatorLookup
from app.skills.human_escalation import HumanEscalation
from app.skills.industry_data_extraction import IndustryDataExtraction
from app.skills.market_analysis_synthesis import MarketAnalysisSynthesis
from app.skills.rag_context_retrieval import RAGContextRetrieval
from app.skills.rag_store_indexer import RAGStoreIndexer
from app.skills.registry import SkillRegistry
from app.skills.research_report_generator import ResearchReportGenerator
from app.skills.web_market_search import WebMarketSearch
from app.prompts.loader import AgentPromptClient
from app.prompts.invalidator import PromptCacheInvalidator

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown hooks."""
    setup_logging()
    logger.info(
        "Market Research Agent starting on %s:%d",
        settings.HOST,
        settings.PORT,
    )

    # Initialize Redis manager
    redis_manager = RedisManager(
        settings.REDIS_URL,
        research_cache_ttl=settings.RESEARCH_CACHE_TTL,
        economic_cache_ttl=settings.ECONOMIC_DATA_CACHE_TTL,
        news_cache_ttl=settings.NEWS_CACHE_TTL,
    )

    # Initialize API clients
    tavily_client = TavilySearchClient(
        settings.TAVILY_API_KEY,
        redis_manager,
        mcp_server_url=settings.TAVILY_MCP_SERVER_URL,
    )
    world_bank_client = WorldBankClient(settings.WORLD_BANK_BASE_URL, redis_manager)
    news_client = GNewsClient(settings.GNEWS_API_KEY, redis_manager)

    # Initialize Kafka producers
    trace_producer = TraceProducer(settings.KAFKA_BOOTSTRAP_SERVERS)
    await trace_producer.start()
    audit_producer = AuditProducer(settings.KAFKA_BOOTSTRAP_SERVERS)
    await audit_producer.start()

    # Initialize Anthropic client (lazy — only if API key present)
    anthropic_client = None
    api_key = settings.ANTHROPIC_API_KEY
    if api_key:
        masked = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "***"
        logger.info(
            "MRA_ANTHROPIC_API_KEY loaded (%s, %d chars), model=%s",
            masked,
            len(api_key),
            settings.LLM_MODEL,
        )
        try:
            import anthropic

            anthropic_client = anthropic.AsyncAnthropic(
                api_key=api_key,
                timeout=120.0,
            )
            logger.info("Anthropic client initialized — live LLM mode")
        except Exception as exc:
            logger.warning("Failed to initialize Anthropic client: %s", exc)
    else:
        logger.warning(
            "No Anthropic API key — running in stub mode. "
            "Set MRA_ANTHROPIC_API_KEY on Railway for live results."
        )

    # Initialize circuit breakers
    circuit_breakers = create_circuit_breakers(settings)

    # Initialize skill registry with all 8 skills
    skill_registry = SkillRegistry()
    skill_registry.register(WebMarketSearch(tavily_client, news_client))
    skill_registry.register(IndustryDataExtraction(tavily_client))
    skill_registry.register(
        MarketAnalysisSynthesis(
            anthropic_client=anthropic_client,
            model=settings.LLM_MODEL,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
        )
    )
    skill_registry.register(EconomicIndicatorLookup(world_bank_client))
    skill_registry.register(
        RAGContextRetrieval(settings.RAG_SERVICE_URL, enabled=settings.RAG_ENABLED)
    )
    skill_registry.register(
        ResearchReportGenerator(
            anthropic_client=anthropic_client,
            model=settings.LLM_MODEL,
            max_tokens=settings.LLM_MAX_TOKENS,
        )
    )
    skill_registry.register(
        RAGStoreIndexer(settings.RAG_SERVICE_URL, enabled=settings.RAG_ENABLED)
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

    # Initialize market researcher (skill-based PAOR engine)
    researcher = MarketResearcher(
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

    # Initialize executor (thin wrapper — guardrails handled by MarketResearcher)
    executor = MRAExecutor(
        researcher=researcher,
        redis_manager=redis_manager,
        trace_producer=trace_producer,
        audit_producer=audit_producer,
    )
    routes.executor = executor

    if settings.TAVILY_API_KEY:
        logger.info("Tavily API key configured — live web search mode")
    else:
        logger.warning("No Tavily API key — web search disabled")

    logger.info(
        "MRA initialized: %d skills, RBAC=%s, %d circuit breakers",
        len(skill_registry.get_all_skills()),
        settings.RBAC_ENABLED,
        len(circuit_breakers),
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
    await executor.close()
    if anthropic_client:
        try:
            await anthropic_client.close()
        except Exception:
            pass
    routes.executor = None
    logger.info("Market Research Agent shut down")


app = FastAPI(
    title="Market Research Agent Service",
    description="Market research, sizing, and competitive analysis agent with 8 skills",
    version="0.2.0",
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
