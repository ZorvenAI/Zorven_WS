"""Logging setup for Intelligence Loop Agent."""

import logging

from app.core.config import settings


def setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format="[%(levelname)s] %(asctime)s %(name)s %(message)s",
    )
