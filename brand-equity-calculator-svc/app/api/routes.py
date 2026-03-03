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

    # Prefer X-Forwarded-For (set by reverse proxies like Kong/Railway)
    # over request.client.host which is typically the proxy's IP.
    forwarded = http_request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    else:
        client_ip = http_request.client.host if http_request.client else "unknown"
    return await executor.calculate(request, client_ip)
