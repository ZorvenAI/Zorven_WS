"""FastAPI application — Odoo MCP Server.

Bridges AI agents and Odoo ERP by exposing Odoo module APIs as MCP tools.
Supports multi-tenancy, RBAC, and RAG integration.
"""

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes
from app.api.routes import router
from app.cache.redis_manager import RedisManager
from app.core.config import settings
from app.core.logging_config import setup_logging
from app.mcp import transport
from app.mcp.transport import mcp_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialize dependencies on startup, clean up on shutdown."""
    setup_logging()
    logger.info("Odoo MCP Server starting on %s:%d", settings.HOST, settings.PORT)

    # Redis (fail-open — service works without it, just no caching)
    redis_manager = RedisManager(settings.REDIS_URL)
    routes.redis_manager = redis_manager

    # ── Vertex AI RAG (direct integration) ──
    tenant_resolver = None
    vertex_adapter = None

    if settings.RAG_ENABLED:
        if settings.DATABASE_URL:
            try:
                from app.rag.tenant_resolver import TenantDataStoreResolver

                tenant_resolver = TenantDataStoreResolver(
                    database_url=settings.DATABASE_URL,
                    redis_manager=redis_manager,
                    default_data_store_id=settings.VERTEX_AI_DATA_STORE_ID,
                )
                await tenant_resolver.init()
                logger.info("TenantDataStoreResolver initialized")
            except Exception as exc:
                logger.warning("TenantDataStoreResolver init failed: %s", exc)
                tenant_resolver = None

        try:
            from app.rag.vertex_ai_adapter import VertexAIRAGAdapter

            vertex_adapter = VertexAIRAGAdapter(
                project_id=settings.VERTEX_AI_PROJECT_ID,
                location=settings.VERTEX_AI_LOCATION,
                default_data_store_id=settings.VERTEX_AI_DATA_STORE_ID,
                mock_mode=settings.VERTEX_AI_MOCK_MODE,
                tenant_resolver=tenant_resolver,
            )
            logger.info(
                "VertexAIRAGAdapter initialized (mock=%s)", settings.VERTEX_AI_MOCK_MODE
            )
        except Exception as exc:
            logger.warning("VertexAIRAGAdapter init failed: %s", exc)
            vertex_adapter = None

    # RAGClient facade (Vertex AI direct or HTTP fallback)
    from app.rag.client import RAGClient

    rag_client = RAGClient(
        base_url=settings.RAG_SERVICE_URL,
        vertex_adapter=vertex_adapter,
    )
    routes.rag_client = rag_client

    # MCP server (optional — only if mcp SDK is available)
    try:
        from app.mcp.server import create_mcp_server

        mcp_srv = create_mcp_server()
        transport.mcp_server = mcp_srv
        logger.info("MCP server initialized with tools/resources/prompts")
    except Exception as exc:
        logger.warning("MCP server not initialized: %s", exc)

    if settings.SERVICE_TOKEN == "dev-service-token":
        logger.warning(
            "Using default SERVICE_TOKEN — set ODOO_MCP_SERVICE_TOKEN in production"
        )

    rag_backend = "vertex_ai" if vertex_adapter else "http_fallback"
    logger.info(
        "Odoo MCP Server ready (transport=%s, rag=%s)",
        settings.MCP_TRANSPORT,
        rag_backend,
    )

    yield

    transport.mcp_server = None
    await rag_client.close()
    if tenant_resolver:
        await tenant_resolver.close()
    await redis_manager.close()
    routes.redis_manager = None
    routes.rag_client = None
    logger.info("Odoo MCP Server shut down")


app = FastAPI(
    title="Odoo MCP Server",
    description="Model Context Protocol server bridging AI agents and Odoo ERP",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
origins = [
    origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(mcp_router)
