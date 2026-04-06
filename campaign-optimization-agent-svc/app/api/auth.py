"""X-Service-Token + X-Tenant-ID authentication for Campaign Optimization Agent."""

from fastapi import Header, HTTPException

from app.core.config import settings


async def verify_service_token(
    x_service_token: str = Header(...),
) -> str:
    """Verify X-Service-Token header matches configured token."""
    if x_service_token != settings.SERVICE_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid service token")
    return x_service_token


async def verify_tenant_id(
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
) -> str:
    """Extract and validate X-Tenant-ID header."""
    if not x_tenant_id or not x_tenant_id.strip():
        raise HTTPException(
            status_code=400, detail="X-Tenant-ID header required"
        )
    return x_tenant_id.strip()
