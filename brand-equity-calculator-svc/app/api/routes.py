"""API routes — GET /health + POST /v1/calculate + POST /v1/export."""

import logging
import re
from typing import TYPE_CHECKING, Optional

from fastapi import APIRouter, HTTPException, Request

from app.api.schemas import (
    BrandEquityRequest,
    BrandEquityResponse,
    ExportRequest,
    ExportResponse,
    HealthResponse,
)

if TYPE_CHECKING:
    from app.cache.redis_manager import RedisManager
    from app.services.brand_equity_executor import BrandEquityExecutor

logger = logging.getLogger(__name__)

router = APIRouter()

# Set by the lifespan hook in main.py.
executor: Optional["BrandEquityExecutor"] = None
redis_manager: Optional["RedisManager"] = None


def _get_client_ip(http_request: Request) -> str:
    """Extract client IP from X-Forwarded-For or fallback to direct IP."""
    forwarded = http_request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return http_request.client.host if http_request.client else "unknown"


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

    client_ip = _get_client_ip(http_request)
    return await executor.calculate(request, client_ip)


@router.post("/v1/export", response_model=ExportResponse)
async def export_report(
    request: ExportRequest,
    http_request: Request,
) -> ExportResponse:
    """Generate a PDF report and email it to the user.

    Public endpoint — no authentication required.
    Rate-limited by client IP (3 exports/minute).
    """
    # Rate limit exports (stricter than calculate)
    if redis_manager is not None:
        allowed = await redis_manager.check_export_rate_limit(
            _get_client_ip(http_request)
        )
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="Too many export requests. Please try again in a minute.",
            )

    email = request.email.strip()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise HTTPException(status_code=400, detail="Invalid email address.")

    from app.services.pdf_generator import generate_brand_equity_pdf
    from app.services.email_sender import EmailResult, send_report_email

    try:
        pdf_bytes = generate_brand_equity_pdf(request.result.model_dump())
    except Exception as exc:
        logger.error("PDF generation failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500, detail="Failed to generate PDF report."
        ) from exc

    result = await send_report_email(
        to_email=email,
        company_name=request.result.company_name,
        overall_score=request.result.overall_score,
        pdf_bytes=pdf_bytes,
    )

    if result == EmailResult.NOT_CONFIGURED:
        raise HTTPException(
            status_code=503,
            detail="Email service is not configured. Please contact support.",
        )
    if result == EmailResult.SEND_FAILED:
        raise HTTPException(
            status_code=502,
            detail=(
                "Failed to send report email. The email service is currently "
                "unavailable. Please try again later."
            ),
        )

    return ExportResponse(
        success=True,
        message=f"Report sent to {email} successfully.",
    )
