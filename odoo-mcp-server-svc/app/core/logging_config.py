"""Structured logging configuration for Odoo MCP Server."""

import logging
import sys

from app.core.config import settings


def setup_logging() -> None:
    """Configure logging with structured format, suppress noisy loggers."""
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
        force=True,
    )

    # Suppress noisy loggers
    for name in ("uvicorn.access", "httpx", "xmlrpc.client", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
