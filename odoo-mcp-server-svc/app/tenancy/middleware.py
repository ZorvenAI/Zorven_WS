"""FastAPI dependency for multi-tenant request resolution.

Usage in a route::

    @router.get("/some-endpoint")
    async def handler(ctx: TenantContext = Depends(get_tenant_context)):
        ...

The module-level ``tenant_resolver`` is initialised by the application
lifespan hook in ``app/main.py``.
"""

import logging
from typing import Optional

from fastapi import HTTPException, Request

from app.tenancy.models import TenantContext
from app.tenancy.resolver import TenantResolver

logger = logging.getLogger(__name__)

# Set by lifespan — remains None until startup completes.
tenant_resolver: Optional[TenantResolver] = None


async def get_tenant_context(request: Request) -> TenantContext:
    """FastAPI dependency: extract tenant from X-Tenant-ID header, resolve context.

    Returns a fully authenticated TenantContext or raises an appropriate
    HTTPException (401 for auth failures, 403 for access issues, 500 for
    uninitialized resolver).
    """
    if tenant_resolver is None:
        logger.error("Tenant resolver not initialised — rejecting request")
        raise HTTPException(
            status_code=500,
            detail="Tenant resolver not initialised",
        )

    tenant_id = request.headers.get("x-tenant-id", "default")

    try:
        context = await tenant_resolver.resolve(tenant_id)
    except Exception as exc:
        exc_name = type(exc).__name__
        if "NotFound" in exc_name:
            logger.warning("Tenant not found: %s", tenant_id)
            raise HTTPException(
                status_code=401,
                detail=f"Tenant '{tenant_id}' not found",
            )
        if "Authentication" in exc_name:
            logger.warning("Authentication failed for tenant %s: %s", tenant_id, exc)
            raise HTTPException(
                status_code=401,
                detail=f"Authentication failed for tenant '{tenant_id}'",
            )
        if "Denied" in exc_name or "Access" in exc_name:
            logger.warning("Access denied for tenant %s: %s", tenant_id, exc)
            raise HTTPException(
                status_code=403,
                detail=f"Access denied for tenant '{tenant_id}'",
            )

        logger.exception("Unexpected error resolving tenant %s", tenant_id)
        raise HTTPException(
            status_code=500,
            detail="Internal error resolving tenant context",
        )

    return context
