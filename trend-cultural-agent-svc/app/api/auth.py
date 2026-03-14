"""Service-to-service authentication via X-Service-Token header."""

from fastapi import Header, HTTPException

from app.core.config import settings


async def verify_service_token(
    x_service_token: str = Header(..., alias="X-Service-Token"),
) -> str:
    """Verify the X-Service-Token header matches the expected value."""
    if x_service_token != settings.SERVICE_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid service token")
    return x_service_token
