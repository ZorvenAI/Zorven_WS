"""Brand equity executor — orchestrates cache, rate limiting, and Claude API.

Flow:
  1. Check IP-based rate limit
  2. Build cache key from normalized inputs
  3. Check Redis cache (24h TTL)
  4. Call Claude API (or return 503 if unavailable)
  5. Cache result
  6. Return BrandEquityResponse
"""

import logging
from typing import Any, Optional

from fastapi import HTTPException

from app.api.schemas import (
    BrandEquityRequest,
    BrandEquityResponse,
    Competitor,
    DimensionScore,
)
from app.cache.redis_manager import RedisManager
from app.services.claude_client import ClaudeClient

logger = logging.getLogger(__name__)


class BrandEquityExecutor:
    """Main service — evaluates brand equity via Claude AI."""

    def __init__(
        self,
        redis_manager: Optional[RedisManager] = None,
        claude_client: Any = None,
        prompt_loader: Any = None,
    ) -> None:
        self.redis_manager = redis_manager
        self.claude_client = (
            ClaudeClient(claude_client, prompt_loader=prompt_loader)
            if claude_client
            else None
        )

    async def calculate(
        self,
        request: BrandEquityRequest,
        client_ip: str,
    ) -> BrandEquityResponse:
        """Evaluate brand equity for the given company."""

        # 1. Rate limit by IP
        if self.redis_manager:
            allowed = await self.redis_manager.check_rate_limit(client_ip)
            if not allowed:
                raise HTTPException(
                    status_code=429,
                    detail=(
                        "Rate limit exceeded. "
                        "Please wait a minute before trying again."
                    ),
                )

        # 2. Build cache key
        cache_key = ""
        if self.redis_manager:
            cache_key = RedisManager.build_cache_key(
                request.company_name,
                request.address,
                request.website,
                request.industry_type,
                request.business_size,
                request.scope,
            )

            # 3. Check cache
            cached = await self.redis_manager.get_cached_result(cache_key)
            if cached:
                return BrandEquityResponse(**cached)

        # 4. Claude API call (or 503 if unavailable)
        if not self.claude_client:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Brand equity analysis is temporarily unavailable. "
                    "Please try again later."
                ),
            )

        try:
            raw = await self.claude_client.evaluate_brand_equity(request)
        except ValueError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except Exception as exc:
            logger.error(
                "Claude API call failed for %s: %s",
                request.company_name,
                exc,
                exc_info=True,
            )
            # Surface billing/auth errors clearly instead of generic message
            exc_str = str(exc)
            if "credit balance" in exc_str or "billing" in exc_str.lower():
                detail = (
                    "The AI service is currently unavailable due to a billing issue. "
                    "Please try again later."
                )
            elif "authentication" in exc_str.lower() or "api key" in exc_str.lower():
                detail = "The AI service is misconfigured. " "Please contact support."
            else:
                detail = "Brand equity analysis failed. Please try again."
            raise HTTPException(status_code=502, detail=detail) from exc

        # Parse into response model
        response = self._parse_response(request.company_name, raw)

        # 5. Cache result
        if self.redis_manager and cache_key:
            await self.redis_manager.set_cached_result(cache_key, response.model_dump())

        return response

    @staticmethod
    def _parse_response(company_name: str, raw: dict[str, Any]) -> BrandEquityResponse:
        """Convert the raw Claude JSON dict into a validated response."""
        dimensions = [
            DimensionScore(
                name=d.get("name", "Unknown"),
                score=max(0, min(100, int(d.get("score", 0)))),
                weight=float(d.get("weight", 0.0)),
                rationale=d.get("rationale", ""),
                key_factors=d.get("key_factors", []),
            )
            for d in raw.get("dimensions", [])
        ]

        overall = raw.get("overall_score")
        if overall is None and dimensions:
            overall = round(sum(d.score * d.weight for d in dimensions))
        overall = max(0, min(100, int(overall or 0)))

        competitors = [
            Competitor(
                name=c.get("name", "Unknown"),
                headquarters=c.get("headquarters", ""),
                estimated_score=max(0, min(100, int(c.get("estimated_score", 0)))),
                strengths=c.get("strengths", []),
                weaknesses=c.get("weaknesses", []),
            )
            for c in raw.get("competitors", [])
        ]

        return BrandEquityResponse(
            company_name=company_name,
            overall_score=overall,
            dimensions=dimensions,
            competitors=competitors,
            formula_explanation=raw.get("formula_explanation", ""),
            derivation=raw.get("derivation", ""),
            limitations=raw.get("limitations", []),
            recommendations=raw.get("recommendations", []),
            methodology="ISO 20671:2019",
        )
