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

    # MCP server (optional — only if mcp SDK is available)
    try:
        from app.mcp.server import create_mcp_server

        mcp_srv = create_mcp_server()
        transport.mcp_server = mcp_srv
        logger.info("MCP server initialized with tools/resources/prompts")
    except Exception as exc:
        logger.warning("MCP server not initialized: %s", exc)

    logger.info("Odoo MCP Server ready (transport=%s)", settings.MCP_TRANSPORT)

    yield

    transport.mcp_server = None
    await redis_manager.close()
    routes.redis_manager = None
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
