"""M-02 · Service-token auth dependency for internal admin endpoints."""

from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, status

from app.core.config import settings


async def verify_service_token(
    x_service_token: str | None = Header(default=None, alias="X-Service-Token"),
) -> None:
    expected = settings.SERVICE_TOKEN

    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SERVICE_TOKEN not configured.",
        )

    if not x_service_token or not hmac.compare_digest(x_service_token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid X-Service-Token.",
        )
