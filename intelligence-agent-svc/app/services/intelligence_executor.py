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

import hashlib
import json
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
from app.prompts.fallbacks import FALLBACK_COMPANY_LOOKUP
from app.prompts.loader import AgentPromptClient
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
        prompt_loader: Optional[AgentPromptClient] = None,
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
        self.prompt_loader = prompt_loader

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

        # Check result cache — canonical JSON + hash for stable, fixed-length keys
        cache_payload = json.dumps(
            {
                "prompt": request.input_prompt,
                "context": request.input_context,
                "config": config,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        cache_hash = hashlib.sha256(cache_payload.encode()).hexdigest()[:16]
        cache_key = f"{tenant_id}:{cache_hash}"
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

        # 1b. Derive financial metrics from input_context when GCS unavailable
        if financial_data is None and input_context.get("base_revenue"):
            growth = float(input_context.get("growth_rate", 0.05))
            margin = float(input_context.get("profit_margin", 0.10))
            financial_data = {
                "revenue_growth": growth,
                "profit_margin": margin,
            }
            # Include market share if available from Gemini lookup
            ctx_market_share = input_context.get("market_share")
            if ctx_market_share is not None:
                financial_data["market_share"] = float(ctx_market_share)
            logger.info(
                "Derived financial data from input_context: "
                "growth=%.2f, margin=%.2f, market_share=%s",
                growth,
                margin,
                ctx_market_share,
            )

        # 1c. Gemini fallback — look up company data if input_context is empty
        if financial_data is None and not input_context.get("base_revenue"):
            company_name = input_context.get(
                "company_name"
            ) or self._extract_company_name(request.input_prompt)
            if company_name and self.gemini_client:
                logger.info(
                    "No financial data in context — looking up '%s' via Gemini",
                    company_name,
                )
                # Check Redis cache first for consistent results across flows
                gemini_data = None
                if self.redis_manager:
                    gemini_data = await self.redis_manager.get_company_data(
                        company_name
                    )
                    if gemini_data:
                        logger.info(
                            "Company data cache HIT for '%s'", company_name
                        )
                if gemini_data is None:
                    gemini_data = await self._lookup_company_data(company_name)
                    # Cache the result for consistent results across flows
                    if gemini_data and self.redis_manager:
                        await self.redis_manager.set_company_data(
                            company_name, gemini_data
                        )
                if gemini_data:
                    for key in (
                        "company_name",
                        "sector",
                        "base_revenue",
                        "growth_rate",
                        "brand_awareness",
                        "profit_margin",
                        "customer_loyalty",
                        "market_share",
                    ):
                        if key in gemini_data and key not in input_context:
                            input_context[key] = gemini_data[key]
                    # Re-derive financial_data from enriched context
                    if input_context.get("base_revenue"):
                        growth = float(input_context.get("growth_rate", 0.05))
                        margin = float(
                            input_context.get("profit_margin", 0.10)
                        )
                        financial_data = {
                            "revenue_growth": growth,
                            "profit_margin": margin,
                        }
                        ctx_market_share = input_context.get("market_share")
                        if ctx_market_share is not None:
                            financial_data["market_share"] = float(
                                ctx_market_share
                            )
                    # Refresh sector from Gemini data
                    sector = str(input_context.get("sector", sector))
                    logger.info(
                        "Enriched context from Gemini: sector=%s, "
                        "base_revenue=%s",
                        sector,
                        input_context.get("base_revenue"),
                    )

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
            previous_outputs, input_context, horizon_years, sector=sector
        )

        # 4b. Abort if no revenue data — cannot produce a valid valuation
        if not projected_revenues:
            company = input_context.get("company_name", "the requested brand")
            logger.warning(
                "ISO valuation aborted for tenant %s: no revenue data for '%s'",
                tenant_id,
                company,
            )
            return ExecuteResponse(
                findings=[
                    f"Unable to calculate brand equity for '{company}'.",
                    "No revenue or financial data could be determined.",
                    f"Sector: {sector}.",
                ],
                recommendations=[
                    "Provide the company's annual revenue in the request "
                    "(e.g., 'Calculate brand equity for Nike with $51B revenue').",
                    "Try a well-known publicly traded company whose financials "
                    "are available (e.g., Apple, Nike, Tesla).",
                    "Upload financial statements to enable accurate valuation.",
                ],
                analysis_type="iso_valuation",
                rationale=(
                    f"Brand equity valuation requires revenue data. "
                    f"No financial data was found for '{company}' from "
                    f"AI lookup, user input, or discovery research."
                ),
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

        # Override behavioral metrics with input_context if provided
        # (Gemini-estimated data is more accurate than generic discovery)
        ctx_awareness = input_context.get("brand_awareness")
        if ctx_awareness is not None:
            if behavioral_data is None:
                behavioral_data = {}
            behavioral_data["brand_awareness"] = float(ctx_awareness)
            logger.info(
                "Using brand_awareness from input_context: %.1f",
                float(ctx_awareness),
            )
        ctx_loyalty = input_context.get("customer_loyalty")
        if ctx_loyalty is not None:
            if behavioral_data is None:
                behavioral_data = {}
            behavioral_data["customer_loyalty"] = float(ctx_loyalty)
            logger.info(
                "Using customer_loyalty from input_context: %.1f",
                float(ctx_loyalty),
            )
        legal_data = input_context.get("legal_data")
        # Pass company name as brand seed for deterministic per-brand variation
        brand_seed = str(input_context.get("company_name", ""))
        bsi_result = self.bsi_calculator.derive_index(
            financial_data=financial_data,
            behavioral_data=behavioral_data,
            legal_data=legal_data,
            brand_seed=brand_seed,
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

        # 8. Calculate NPV (with terminal value)
        terminal_growth = settings.DEFAULT_TERMINAL_GROWTH_RATE
        valuation = self.royalty_engine.calculate_npv(
            projected_revenues=projected_revenues,
            royalty_rate=royalty_rate,
            discount_rate=discount_rate,
            tax_rate=tax_rate,
            terminal_growth_rate=terminal_growth,
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

        # 1. Run gap analysis (with optional skill context from orchestrator)
        skill_context = request.config.get("skill_context", "")
        gap_result = await self.gap_analyzer.analyze(
            previous_outputs=request.previous_outputs,
            config=request.config,
            gemini_client=self.gemini_client,
            skill_context=skill_context,
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
    # Gemini company data lookup
    # -----------------------------------------------------------------------

    # Stop words — common words that are NOT company names.
    _STOP_WORDS = frozenset(
        {
            "the",
            "a",
            "an",
            "my",
            "our",
            "this",
            "that",
            "i",
            "we",
            "can",
            "you",
            "please",
            "brand",
            "equity",
            "value",
        }
    )

    @staticmethod
    def _extract_company_name(input_prompt: str) -> str | None:
        """Extract the company/brand name from a user prompt via regex."""
        import re

        patterns = [
            r"(?:brand equity|brand valuation|brand value|brand strength)"
            r"(?:\s+(?:for|of|for the))?\s+(?:the\s+)?"
            r"([A-Z][A-Za-z0-9\s&'.-]+?)(?:\s+brand)?[?.!,]?\s*$",
            r"(?:calculate|analyze|analyse|evaluate|assess)"
            r"(?:\s+(?:the\s+)?brand\s+(?:equity|value|valuation|"
            r"strength)\s+(?:for|of))?\s+(?:the\s+)?"
            r"([A-Z][A-Za-z0-9\s&'.-]+?)(?:\s+brand)?[?.!,]?\s*$",
            r"(?:for|of)\s+(?:the\s+)?"
            r"([A-Z][A-Za-z0-9\s&'.-]+?)(?:\s+brand)[?.!,]?\s*$",
            r"([A-Z][A-Za-z0-9&'.-]+?)(?:'s)\s+"
            r"(?:brand\s+)?(?:equity|value|valuation|strength)",
        ]
        for pattern in patterns:
            match = re.search(pattern, input_prompt, re.IGNORECASE)
            if match:
                name = match.group(1).strip().rstrip(".,!?")
                if (
                    len(name) > 1
                    and name.lower()
                    not in IntelligenceExecutor._STOP_WORDS
                ):
                    return name
        return None

    async def _lookup_company_data(self, company_name: str) -> dict[str, Any] | None:
        """Look up real financial data for a company via Gemini AI.

        Returns a dict with company_name, sector, base_revenue, growth_rate,
        brand_awareness, profit_margin, customer_loyalty, market_share — or
        None if the data cannot be determined.
        """
        import json as _json

        try:
            if self.gemini_client is None:
                return None

            model = self.gemini_client.GenerativeModel(settings.GEMINI_MODEL)

            # Load prompt from prompt-optimization-svc (or fallback)
            if self.prompt_loader:
                prompt = await self.prompt_loader.load(
                    "zorven-intelligence-company-lookup",
                    variables={"company_name": company_name},
                    fallback=FALLBACK_COMPANY_LOOKUP,
                )
            else:
                prompt = FALLBACK_COMPANY_LOOKUP.replace(
                    "{company_name}", company_name
                )

            response = model.generate_content(prompt)
            text = response.text.strip()

            if "NOT_FOUND" in text.upper():
                logger.info(
                    "Gemini: company '%s' not found or private",
                    company_name,
                )
                return None

            # Strip markdown fences if present
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

            data = _json.loads(text, strict=False)

            # Validate required fields
            required = {
                "company_name",
                "sector",
                "base_revenue",
                "growth_rate",
                "brand_awareness",
                "profit_margin",
            }
            if not required.issubset(data.keys()):
                logger.warning(
                    "Gemini response missing fields for %s: %s",
                    company_name,
                    required - data.keys(),
                )
                return None

            # Coerce and validate types
            data["base_revenue"] = int(float(data["base_revenue"]))
            data["growth_rate"] = float(data["growth_rate"])
            data["brand_awareness"] = int(float(data["brand_awareness"]))
            data["profit_margin"] = float(data["profit_margin"])

            if "customer_loyalty" in data and data["customer_loyalty"] is not None:
                data["customer_loyalty"] = int(float(data["customer_loyalty"]))
            if "market_share" in data and data["market_share"] is not None:
                data["market_share"] = float(data["market_share"])

            if data["base_revenue"] <= 0:
                logger.warning(
                    "Gemini returned non-positive revenue for %s",
                    company_name,
                )
                return None

            # Validate the returned company matches the request
            input_clean = (
                company_name.lower().replace(".", "").replace(",", "").strip()
            )
            result_clean = (
                data["company_name"]
                .lower()
                .replace(".", "")
                .replace(",", "")
                .strip()
            )
            result_words = result_clean.split()
            input_words = input_clean.split()

            match_found = (
                input_clean in result_clean
                or result_clean in input_clean
                or any(w in result_clean for w in input_words if len(w) > 2)
                or any(
                    rw.startswith(input_clean[:4])
                    for rw in result_words
                    if len(input_clean) >= 4
                )
                or result_clean.startswith(input_clean[:4])
            )

            if not match_found:
                logger.warning(
                    "Gemini returned mismatched company: asked for "
                    "'%s', got '%s' — rejecting",
                    company_name,
                    data["company_name"],
                )
                return None

            logger.info(
                "Gemini provided data for %s: sector=%s, revenue=$%s, "
                "awareness=%s",
                company_name,
                data.get("sector"),
                f"{data.get('base_revenue', 0):,}",
                data.get("brand_awareness"),
            )
            return data

        except Exception as e:
            logger.warning(
                "Gemini company lookup failed for %s: %s",
                company_name,
                e,
            )
            return None

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
