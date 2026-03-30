"""Service-to-service authentication for the CAA API."""

import logging

from fastapi import Header, HTTPException

from app.core.config import settings

logger = logging.getLogger(__name__)


async def verify_service_token(
    x_service_token: str = Header("", alias="X-Service-Token"),
) -> str:
    """Verify X-Service-Token header matches configured token."""
    if not x_service_token or x_service_token != settings.SERVICE_TOKEN:
        logger.warning("Unauthorized request (invalid X-Service-Token)")
        raise HTTPException(status_code=401, detail="Invalid service token")
    return x_service_token
