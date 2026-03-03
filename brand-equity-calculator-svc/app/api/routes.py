"""API routes — GET /health + POST /v1/calculate."""

import logging
from typing import TYPE_CHECKING, Optional

from fastapi import APIRouter, HTTPException, Request

from app.api.schemas import BrandEquityRequest, BrandEquityResponse, HealthResponse

if TYPE_CHECKING:
    from app.services.brand_equity_executor import BrandEquityExecutor

logger = logging.getLogger(__name__)

router = APIRouter()

# Set by the lifespan hook in main.py.
executor: Optional["BrandEquityExecutor"] = None


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()


@router.post("/v1/calculate", response_model=BrandEquityResponse)
async def calculate(
    request: BrandEquityRequest,
    http_request: Request,
) -> BrandEquityResponse:
    """Evaluate brand equity using ISO 20671:2019 via Claude AI.

    This is a public endpoint — no authentication required.
    Rate-limited by client IP (default 5 requests/minute).
    """
    if executor is None:
        raise HTTPException(
            status_code=503,
            detail="Brand equity analysis is temporarily unavailable. Please try again later.",
        )

    # Determine client IP for rate limiting.
    # Only trust X-Forwarded-For from a known trusted proxy (Kong sets
    # X-Kong-Proxy: true). Otherwise use the direct client address to
    # prevent spoofing by malicious callers.
    client_ip = http_request.client.host if http_request.client else "unknown"
    trusted_proxy = http_request.headers.get("x-kong-proxy", "").lower() == "true"
    if trusted_proxy:
        forwarded = http_request.headers.get("x-forwarded-for")
        if forwarded:
            forwarded_ips = [ip.strip() for ip in forwarded.split(",") if ip.strip()]
            if forwarded_ips:
                client_ip = forwarded_ips[0]

    return await executor.calculate(request, client_ip)
