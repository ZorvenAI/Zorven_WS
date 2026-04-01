"""X-Service-Token authentication for CGA service."""

from fastapi import Header, HTTPException

from app.core.config import settings


async def verify_service_token(
    x_service_token: str = Header(...),
) -> str:
    """Verify X-Service-Token header matches configured token."""
    if x_service_token != settings.SERVICE_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid service token")
    return x_service_token
