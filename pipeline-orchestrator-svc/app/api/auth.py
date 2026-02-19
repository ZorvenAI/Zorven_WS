"""
Service-to-service authentication via X-Service-Token header.

The Django core-api-service sends this token when dispatching jobs.
"""

import logging

from fastapi import HTTPException, Request

from app.core.config import settings

logger = logging.getLogger(__name__)


async def verify_service_token(request: Request) -> None:
    """FastAPI dependency that validates the X-Service-Token header."""
    token = request.headers.get("X-Service-Token", "")
    if not token or token != settings.SERVICE_TOKEN:
        logger.warning(
            "Invalid service token from %s",
            request.client.host if request.client else "unknown",
        )
        raise HTTPException(status_code=403, detail="Invalid service token")
