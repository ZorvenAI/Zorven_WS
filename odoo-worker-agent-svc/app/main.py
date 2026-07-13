"""
Odoo Worker Agent Service — FastAPI application entry point.

Multi-persona AI worker agent for Odoo ERP operations.
Sits between the pipeline orchestrator and odoo-mcp-server-svc,
providing intelligent persona-based reasoning via a PAOR loop.
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
from app.messaging.trace_producer import TraceProducer
from app.messaging.audit_producer import AuditProducer
from app.personas.loader import load_all_personas
from app.personas.resolver import PersonaResolver
from app.services.mcp_client import MCPClient
from app.services.circuit_breaker import CircuitBreaker
from app.skills.loader import load_all_skills
from app.skills.registry import SkillRegistry
from app.skills.router import SkillRouter
from app.agent.engine import AgentEngine
from app.agent.llm import GeminiClient
from app.prompts.loader import AgentPromptClient
from app.rbac.preflight import RBACPreflight
from app.rag.client import RAGClient
from app.services.executor import WorkerExecutor

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown hooks."""
    setup_logging()
    logger.info(
        "Odoo Worker Agent starting on %s:%d",
        settings.HOST,
        settings.PORT,
    )

    # Initialize Redis manager
    redis_manager = RedisManager(settings.REDIS_URL)

    # Initialize prompt loader
    prompt_loader = AgentPromptClient(
        redis_url=settings.PROMPT_CACHE_REDIS_URL,
        mlflow_uri=settings.MLFLOW_TRACKING_URI,
        default_ttl=settings.PROMPT_CACHE_TTL,
        fallback_only=settings.PROMPT_FALLBACK_ONLY,
    )
    await prompt_loader.start()

    # Initialize Gemini client (optional)
    gemini_client = None
    if settings.GOOGLE_API_KEY:
        try:
            import google.generativeai as genai

            genai.configure(api_key=settings.GOOGLE_API_KEY)
            gemini_client = GeminiClient(
                model_name=settings.GEMINI_MODEL,
                max_tool_calls_per_step=settings.MAX_TOOL_CALLS_PER_STEP,
                prompt_loader=prompt_loader,
            )
            logger.info("Gemini AI configured (model: %s)", settings.GEMINI_MODEL)
        except Exception as exc:
            logger.warning("Failed to initialize Gemini: %s", exc)
    else:
        logger.info("No Google API key — running in stub mode")

    # Load personas
    personas = load_all_personas(settings.PERSONAS_DIR)
    persona_resolver = PersonaResolver(
        personas=personas,
        gemini_client=gemini_client,
    )
    logger.info("Loaded %d persona(s)", len(personas))

    # Load skills
    skills = load_all_skills()
    skill_registry = SkillRegistry(skills)
    skill_router = SkillRouter(skill_registry)
    logger.info("Loaded %d skill(s)", skill_registry.skill_count)

    # Initialize MCP client with circuit breaker
    circuit_breaker = CircuitBreaker()
    mcp_client = MCPClient(
        base_url=settings.MCP_SERVER_URL,
        timeout=settings.MCP_TIMEOUT,
        circuit_breaker=circuit_breaker,
        service_token=settings.SERVICE_TOKEN,
    )

    # Initialize Kafka producers
    trace_producer = TraceProducer(settings.KAFKA_BOOTSTRAP_SERVERS)
    await trace_producer.start()

    audit_producer = AuditProducer(settings.KAFKA_BOOTSTRAP_SERVERS)
    await audit_producer.start()

    # Initialize RBAC pre-flight
    rbac_preflight = RBACPreflight(
        mcp_client=mcp_client,
        enabled=settings.RBAC_PRE_FLIGHT,
    )

    # Initialize RAG client
    rag_client = RAGClient(
        service_url=settings.RAG_SERVICE_URL,
        enabled=settings.RAG_ENABLED,
    )

    # Initialize agent engine
    agent_engine = AgentEngine(
        gemini_client=gemini_client,
        mcp_client=mcp_client,
        rbac_preflight=rbac_preflight,
        rag_client=rag_client,
        max_steps=settings.MAX_REASONING_STEPS,
        trace_producer=trace_producer,
        audit_producer=audit_producer,
    )

    # Build executor
    executor = WorkerExecutor(
        persona_resolver=persona_resolver,
        skill_router=skill_router,
        agent_engine=agent_engine,
        redis_manager=redis_manager,
        trace_producer=trace_producer,
    )
    routes.executor = executor

    yield  # application runs here

    # Shutdown
    await mcp_client.close()
    await trace_producer.stop()
    await audit_producer.stop()
    await prompt_loader.stop()
    await redis_manager.close()
    routes.executor = None
    logger.info("Odoo Worker Agent shut down")


app = FastAPI(
    title="Odoo Worker Agent Service",
    description="Multi-persona AI worker agent for Odoo ERP operations",
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
