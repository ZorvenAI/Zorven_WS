"""Shared request dependencies — service-token auth and tenant extraction.

Design §15, §16 · scaffolded by A-05, implemented by C-01.

``X-Service-Token`` rather than a JWT, and rather than anything invented here:
§10.2 marks the agent endpoints "X-Service-Token · not exposed publicly", and
the C-01 card is explicit — "mirroring the fleet. Do not invent a new auth
scheme for this service."
"""

from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, Request, status

from app.core.errors import ErrorCode

SERVICE_TOKEN_HEADER = "X-Service-Token"


async def verify_service_token(
    request: Request,
    x_service_token: str | None = Header(default=None, alias=SERVICE_TOKEN_HEADER),
) -> None:
    """Reject any caller without the configured service token.

    ``hmac.compare_digest`` rather than ``==``: token comparison is the one
    place where an early-exit equality check leaks length and prefix through
    timing. The cost is nil and the habit is worth keeping.

    An unset ``SERVICE_TOKEN`` refuses everything rather than allowing
    everything. A service that authenticates nothing because its config is
    missing is the failure mode that looks fine in staging.
    """
    expected = getattr(request.app.state.settings, "SERVICE_TOKEN", "")

    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": ErrorCode.INVALID_JWT,
                "message": (
                    "This service has no SERVICE_TOKEN configured and cannot "
                    "authenticate callers."
                ),
            },
        )

    if not x_service_token or not hmac.compare_digest(x_service_token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": ErrorCode.INVALID_JWT,
                "message": f"A valid {SERVICE_TOKEN_HEADER} header is required.",
            },
        )
