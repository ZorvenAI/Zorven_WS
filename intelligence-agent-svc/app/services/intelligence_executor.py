"""
Intelligence executor — core orchestration service.

Routes incoming requests to the appropriate analysis flow:
  1. ISO 10668 Royalty Relief valuation (config.method = "royalty_relief")
  2. Competitive gap analysis (config.analysis_type = "competitive_gap")
  3. General AI-powered analysis (fallback)

Wire order:
  1. Check rate limit
  2. Check result cache
  3. Determine analysis type from config
  4. Execute analysis flow
  5. Cache result
  6. Return ExecuteResponse
"""

import logging
from typing import Any, Optional

from fastapi import HTTPException

from app.api.schemas import ExecuteRequest, ExecuteResponse
from app.cache.redis_manager import RedisManager
from app.core.config import settings
from app.logic.analysis.competitive_gap import CompetitiveGapAnalyzer
from app.logic.analysis.theme_analyzer import ThemeAnalyzer
from app.logic.iso_engine.bsi_calculator import BSICalculator
from app.logic.iso_engine.proxy_engine import ProxyEngine
from app.logic.iso_engine.royalty_relief import RoyaltyReliefEngine
from app.services.rag_adapter import RAGAdapter
from app.services.storage_service import StorageService

logger = logging.getLogger(__name__)


class IntelligenceExecutor:
    """Orchestrates analysis flows: ISO valuation and competitive gap analysis."""

    def __init__(
        self,
        royalty_engine: RoyaltyReliefEngine,
        bsi_calculator: BSICalculator,
        proxy_engine: ProxyEngine,
        gap_analyzer: CompetitiveGapAnalyzer,
        theme_analyzer: ThemeAnalyzer,
        storage_service: Optional[StorageService] = None,
        rag_adapter: Optional[RAGAdapter] = None,
        redis_manager: Optional[RedisManager] = None,
        gemini_client: Any = None,
    ) -> None:
        self.royalty_engine = royalty_engine
        self.bsi_calculator = bsi_calculator
        self.proxy_engine = proxy_engine
        self.gap_analyzer = gap_analyzer
        self.theme_analyzer = theme_analyzer
        self.storage_service = storage_service
        self.rag_adapter = rag_adapter
        self.redis_manager = redis_manager
        self.gemini_client = gemini_client

    async def execute(self, request: ExecuteRequest, tenant_id: str) -> ExecuteResponse:
        """
        Route to the appropriate analysis based on config.

        Routing logic:
          - config.method == "royalty_relief" → ISO valuation
          - config.analysis_type == "competitive_gap" → gap analysis
          - Otherwise → general analysis
        """
        config = request.config

        # Rate limiting
        if self.redis_manager:
            allowed = await self.redis_manager.check_rate_limit(
                tenant_id, limit=settings.RATE_LIMIT_PER_MINUTE
            )
            if not allowed:
                logger.warning("Rate limit exceeded for tenant %s", tenant_id)
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded for tenant {tenant_id}. "
                    f"Max {settings.RATE_LIMIT_PER_MINUTE} requests per minute.",
                )

        # Check result cache
        cache_key = f"{tenant_id}:{request.input_prompt}:{config}"
        if self.redis_manager:
            cached = await self.redis_manager.get_cached_result(cache_key)
            if cached:
                logger.info("Cache hit for tenant %s", tenant_id)
                return ExecuteResponse(**cached)

        # Route to appropriate analysis flow
        method = config.get("method", "")
        analysis_type = config.get("analysis_type", "")

        if method == "royalty_relief" or analysis_type == "iso_valuation":
            response = await self._execute_iso_valuation(request, tenant_id)
        elif analysis_type == "competitive_gap":
            response = await self._execute_gap_analysis(request, tenant_id)
        else:
            response = await self._execute_general_analysis(request, tenant_id)

        # Cache the result
        if self.redis_manager:
            await self.redis_manager.set_cached_result(cache_key, response.model_dump())

        return response

    async def _execute_iso_valuation(
        self, request: ExecuteRequest, tenant_id: str
    ) -> ExecuteResponse:
        """
        ISO 10668 Royalty Relief valuation flow.

        Steps:
          1. Fetch financial data from GCS (or use stub)
          2. Get sector benchmarks from cache
          3. Estimate revenue forecast
          4. Calculate BSI with proxy engine
          5. Select royalty rate based on BSI + sector
          6. Calculate NPV via RoyaltyReliefEngine
          7. Build findings + recommendations
        """
        config = request.config
        input_context = request.input_context
        previous_outputs = request.previous_outputs

        horizon_years = int(config.get("horizon_years", settings.DEFAULT_HORIZON_YEARS))
        tax_rate = float(config.get("tax_rate", settings.DEFAULT_TAX_RATE))
        sector = str(input_context.get("sector", "default"))

        logger.info(
            "ISO valuation for tenant %s: sector=%s, horizon=%d",
            tenant_id,
            sector,
            horizon_years,
        )

        # 1. Fetch financial data from GCS
        financial_data = None
        if self.storage_service:
            financial_data = await self.storage_service.fetch_financial_data(tenant_id)

        # 2. Determine calculation strategy
        data_manifest = {
            "financial_data": financial_data,
            "behavioral_data": previous_outputs.get("behavioral_data"),
            "legal_data": previous_outputs.get("legal_data"),
        }
        strategy = self.proxy_engine.get_calculation_strategy(data_manifest)

        # 3. Get sector benchmarks from cache
        benchmarks = None
        if self.redis_manager:
            benchmarks = await self.redis_manager.get_benchmarks(sector)

        # 4. Estimate revenue forecast
        projected_revenues = self.royalty_engine.estimate_revenues_from_context(
            previous_outputs, input_context, horizon_years
        )

        # 5. Calculate BSI
        behavioral_data = self._extract_behavioral_data(previous_outputs)
        # Derive behavioral metrics from discovery findings if not available
        if behavioral_data is None:
            all_findings = self._collect_findings(previous_outputs)
            if all_findings:
                sentiment = self.theme_analyzer.calculate_sentiment_score(all_findings)
                themes = self.theme_analyzer.extract_themes(all_findings)
                # Derive brand awareness proxy from theme coverage
                brand_themes = [
                    t for t in themes if t["category"] == "brand_perception"
                ]
                awareness = (
                    min(100.0, brand_themes[0]["sentiment"] * 1.1)
                    if brand_themes
                    else None
                )
                behavioral_data = {"sentiment_score": sentiment}
                if awareness is not None:
                    behavioral_data["brand_awareness"] = awareness
                logger.info(
                    "Derived behavioral data from %d discovery findings: "
                    "sentiment=%.1f",
                    len(all_findings),
                    sentiment,
                )
        legal_data = input_context.get("legal_data")
        bsi_result = self.bsi_calculator.derive_index(
            financial_data=financial_data,
            behavioral_data=behavioral_data,
            legal_data=legal_data,
        )

        # 6. Select royalty rate (BSI can influence rate selection)
        royalty_rate = RoyaltyReliefEngine.select_royalty_rate(sector, benchmarks)
        # Adjust royalty rate based on BSI (higher BSI → higher royalty rate)
        if bsi_result.score > 75:
            royalty_rate *= 1.1  # 10% premium for strong brands
        elif bsi_result.score < 40:
            royalty_rate *= 0.9  # 10% discount for weak brands

        # 7. Get discount rate from cache or use default
        discount_rate = settings.DEFAULT_DISCOUNT_RATE
        if self.redis_manager:
            region = str(input_context.get("region", "global"))
            cached_wacc = await self.redis_manager.get_wacc(region)
            if cached_wacc is not None:
                discount_rate = cached_wacc

        # 8. Calculate NPV
        valuation = self.royalty_engine.calculate_npv(
            projected_revenues=projected_revenues,
            royalty_rate=royalty_rate,
            discount_rate=discount_rate,
            tax_rate=tax_rate,
        )

        # 9. Build rationale
        rationale = RoyaltyReliefEngine.build_rationale(
            valuation, sector, bsi_result.score
        )

        # 10. Build findings and recommendations
        findings = [
            f"Brand value estimated at ${valuation.brand_value_npv:,.2f} "
            f"using Royalty Relief method.",
            f"Brand Strength Index (BSI): {bsi_result.score}/100.",
            f"Calculation strategy: {strategy}.",
            f"Data completeness: {bsi_result.data_completeness:.0%}.",
        ]

        recommendations = self._build_valuation_recommendations(
            bsi_result, valuation, strategy
        )

        return ExecuteResponse(
            findings=findings,
            recommendations=recommendations,
            valuation=valuation,
            bsi=bsi_result,
            methodology="royalty_relief",
            rationale=rationale,
            analysis_type="iso_valuation",
        )

    async def _execute_gap_analysis(
        self, request: ExecuteRequest, tenant_id: str
    ) -> ExecuteResponse:
        """
        Competitive gap analysis from discovery findings.

        Steps:
          1. Run CompetitiveGapAnalyzer (AI or rule-based)
          2. Extract themes via ThemeAnalyzer
          3. Build findings + recommendations
        """
        logger.info("Gap analysis for tenant %s", tenant_id)

        # 1. Run gap analysis
        gap_result = await self.gap_analyzer.analyze(
            previous_outputs=request.previous_outputs,
            config=request.config,
            gemini_client=self.gemini_client,
        )

        # 2. Extract themes from discovery findings
        all_findings = self._collect_findings(request.previous_outputs)
        themes = self.theme_analyzer.extract_themes(all_findings)
        sentiment = self.theme_analyzer.calculate_sentiment_score(all_findings)

        # 3. Build response
        findings = []
        findings.append(
            f"Identified {len(gap_result.get('strengths', []))} competitive strengths "
            f"and {len(gap_result.get('gaps', []))} market gaps."
        )
        findings.append(f"Overall market sentiment: {sentiment:.1f}/100.")

        for theme in themes[:3]:
            findings.append(
                f"Theme: {theme['category']} "
                f"(sentiment: {theme['sentiment']}/100, "
                f"mentioned in {theme['finding_count']} findings)."
            )

        recommendations = []
        for gap in gap_result.get("gaps", [])[:3]:
            recommendations.append(f"Address gap: {gap}")
        for opp in gap_result.get("market_opportunities", [])[:2]:
            recommendations.append(opp)
        if not recommendations:
            recommendations.append(
                "Continue monitoring competitive landscape for emerging opportunities."
            )

        return ExecuteResponse(
            findings=findings,
            recommendations=recommendations,
            analysis_type="competitive_gap",
            gap_analysis=gap_result,
            rationale=f"Analysis based on {len(all_findings)} discovery findings. "
            f"Sentiment score: {sentiment:.1f}/100.",
        )

    async def _execute_general_analysis(
        self, request: ExecuteRequest, tenant_id: str
    ) -> ExecuteResponse:
        """
        General AI-powered analysis fallback.

        Uses theme extraction and sentiment analysis on available data.
        """
        logger.info("General analysis for tenant %s", tenant_id)

        all_findings = self._collect_findings(request.previous_outputs)
        themes = self.theme_analyzer.extract_themes(all_findings)
        sentiment = self.theme_analyzer.calculate_sentiment_score(all_findings)

        findings = [
            f"Analyzed {len(all_findings)} data points from upstream nodes.",
            f"Overall sentiment: {sentiment:.1f}/100.",
        ]
        for theme in themes[:5]:
            findings.append(
                f"Theme: {theme['category']} — "
                f"{', '.join(theme['keywords_found'][:3])} "
                f"(sentiment: {theme['sentiment']}/100)."
            )

        recommendations = [
            "Review the extracted themes for actionable insights.",
            "Cross-reference findings with internal data for validation.",
        ]

        return ExecuteResponse(
            findings=findings,
            recommendations=recommendations,
            analysis_type="general",
            rationale=f"General analysis of {len(all_findings)} findings. "
            f"Extracted {len(themes)} themes with {sentiment:.1f}/100 sentiment.",
        )

    async def close(self) -> None:
        """Clean up resources."""
        if self.redis_manager:
            await self.redis_manager.close()

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _collect_findings(previous_outputs: dict[str, Any]) -> list[str]:
        """Collect all text findings from upstream node outputs."""
        all_findings: list[str] = []
        for node_id, output in previous_outputs.items():
            if isinstance(output, dict):
                findings = output.get("findings", [])
                if isinstance(findings, list):
                    all_findings.extend(str(f) for f in findings)
        return all_findings

    @staticmethod
    def _extract_behavioral_data(
        previous_outputs: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Extract behavioral metrics from discovery/research outputs."""
        for node_id, output in previous_outputs.items():
            if isinstance(output, dict):
                # Check for explicit behavioral data
                if "behavioral_data" in output:
                    return output["behavioral_data"]
                # Derive from discovery findings
                sentiment = output.get("sentiment_score")
                awareness = output.get("brand_awareness")
                if sentiment is not None or awareness is not None:
                    data: dict[str, Any] = {}
                    if sentiment is not None:
                        data["sentiment_score"] = float(sentiment)
                    if awareness is not None:
                        data["brand_awareness"] = float(awareness)
                    return data
        return None

    @staticmethod
    def _build_valuation_recommendations(
        bsi: Any, valuation: Any, strategy: str
    ) -> list[str]:
        """Build actionable recommendations from valuation results."""
        recommendations: list[str] = []

        if bsi.data_completeness < 1.0:
            recommendations.append(
                "Provide complete financial and legal data"
                " for a more accurate valuation."
            )

        if bsi.score < 50:
            recommendations.append(
                "Consider improving brand awareness"
                " and customer loyalty to increase BSI."
            )
        elif bsi.score >= 75:
            recommendations.append(
                "Strong brand — leverage brand equity for premium pricing strategy."
            )

        if strategy == "PRICE_PREMIUM_MODE":
            recommendations.append(
                "Financial data unavailable — valuation used price premium proxy. "
                "Upload financial statements for standard Royalty Relief calculation."
            )

        if not recommendations:
            recommendations.append(
                "Maintain current brand investment levels and monitor BSI quarterly."
            )

        return recommendations
