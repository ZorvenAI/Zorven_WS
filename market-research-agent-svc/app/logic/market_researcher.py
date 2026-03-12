"""
Market Researcher — PAOR-based market research engine using Claude.

Implements the Plan-Act-Observe-Reflect reasoning loop:
  1. PLAN  — Decompose the research query into sub-tasks
  2. ACT   — Execute data gathering in parallel (web, economic, news)
  3. OBSERVE — Compile raw data into structured context
  4. REFLECT — Synthesize findings via Claude
"""

import asyncio
import json
import logging
from typing import Any, Optional

from app.api.schemas import MarketResearchResponse, SourceItem
from app.services.api_clients import GNewsClient, TavilySearchClient, WorldBankClient

logger = logging.getLogger(__name__)

_PLAN_SYSTEM_PROMPT = """\
You are a market research planning assistant. Given a research query, decompose it \
into specific search queries and data requirements.

IMPORTANT — Geographic Scope Detection:
If the user specifies a geographic area (city, town, county, state, region, or country), \
you MUST scope ALL search queries to that area. For example:
- "pizza business in Cranberry PA" → search queries should include "Cranberry PA" or \
"Cranberry Township PA" in every query
- "EV market in Europe" → scope to European countries
- If a local area is specified (city/town/county), set "geographic_scope" to "local" \
and "scope_location" to the area name. For local queries, set indicators to an empty \
list since World Bank data is country-level and not useful for local analysis.
- If a country is specified, set "geographic_scope" to "national".
- If no geography is specified, set "geographic_scope" to "global".

Respond with a JSON object containing:
- "search_queries": list of 2-4 specific web search queries (include location if specified)
- "indicators": list of economic indicator names to fetch \
(options: gdp, gdp_growth, inflation, unemployment, population, gni_per_capita, \
trade_pct_gdp, fdi_net_inflows). Use EMPTY list [] for local/city-level queries.
- "news_queries": list of 1-2 news search queries (include location if specified)
- "countries": list of ISO country codes relevant to the query (default ["WLD"])
- "geographic_scope": one of "local", "national", "regional", "global"
- "scope_location": string — the specific location mentioned (e.g. "Cranberry Township, PA")
- "focus_areas": list of key areas to analyze

Only output valid JSON, no other text."""

_SYNTHESIS_SYSTEM_PROMPT = """\
You are a senior market research analyst. Synthesize the provided raw data into a \
structured market research report.

CRITICAL — Geographic Scope:
If the research query specifies a geographic area (city, town, region, country), \
you MUST scope your entire analysis to that area:
- TAM: the NATIONAL or REGIONAL total market (not global) relevant to the location
- SAM: the metro area or state-level serviceable market
- SOM: the specific local area the user asked about
- Competitors: prioritize LOCAL competitors found in the data; include national chains \
only if they have local presence
- Overview: lead with the LOCAL market context, not global statistics
- "market_position" must be a SHORT phrase (3-8 words max), e.g. "Local market leader", \
"National chain with local presence", "Emerging competitor"
- "description" should be 1-2 concise sentences max

You must respond with a JSON object containing:
- "overview": string — A comprehensive 2-3 paragraph market overview (scoped to the \
geographic area if one was specified)
- "sizing": object — Market sizing with keys "tam", "sam", "som". Each value must be \
an object with "value" (string, e.g. "$1.2B") and "description" (string, 1-2 sentences)
- "competitors": list of objects with "name" (string), "description" (string, 1-2 \
sentences max), "market_position" (string, SHORT 3-8 word phrase)
- "trends": list of 3-7 key industry trend strings
- "findings": list of 5-10 key finding strings (factual, data-backed)
- "recommendations": list of 3-5 actionable recommendation strings
- "confidence": float 0.0-1.0 indicating data quality/completeness
- "methodology": list of strings describing methodology used

Base your analysis on the provided data. Be specific with numbers and citations. \
If data is insufficient for market sizing, indicate that clearly.

Only output valid JSON, no other text."""


class MarketResearcher:
    """PAOR-based market research engine."""

    def __init__(
        self,
        tavily_client: TavilySearchClient,
        world_bank_client: WorldBankClient,
        news_client: GNewsClient,
        anthropic_api_key: str = "",
        model: str = "claude-sonnet-4-20250514",
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> None:
        self.tavily_client = tavily_client
        self.world_bank_client = world_bank_client
        self.news_client = news_client
        self.anthropic_api_key = anthropic_api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._anthropic_client: Any = None

    def _get_anthropic(self) -> Any:
        """Lazy-init Anthropic client."""
        if self._anthropic_client is None and self.anthropic_api_key:
            import anthropic

            self._anthropic_client = anthropic.AsyncAnthropic(
                api_key=self.anthropic_api_key,
                timeout=120.0,
            )
        return self._anthropic_client

    async def research(
        self,
        prompt: str,
        config: dict[str, Any],
        previous_outputs: dict[str, Any],
    ) -> MarketResearchResponse:
        """
        Execute the full PAOR market research loop.

        1. PLAN  — Decompose query into sub-tasks via Claude
        2. ACT   — Gather data from web, World Bank, GNews
        3. OBSERVE — Compile raw context
        4. REFLECT — Synthesize findings via Claude
        """
        # Merge any skill context or config hints
        focus = config.get("focus", "")
        skill_context = config.get("skill_context", "")
        augmented_prompt = prompt
        if focus:
            augmented_prompt += f" (focus: {focus})"

        # 1. PLAN — Decompose the research query
        logger.info("PLAN phase starting for: %s", augmented_prompt[:100])
        research_plan = await self._plan_research(augmented_prompt, skill_context)
        logger.info("PLAN phase complete: %d queries, %d indicators",
                     len(research_plan.get("search_queries", [])),
                     len(research_plan.get("indicators", [])))

        # 2. ACT — Execute data gathering in parallel
        logger.info("ACT phase starting — gathering data from sources")
        web_results, economic_data, news_data = await self._gather_data(
            research_plan, previous_outputs
        )
        logger.info("ACT phase complete: %d web, %d econ, %d news",
                     len(web_results), len(economic_data), len(news_data))

        # 3. OBSERVE — Compile raw context and sources
        raw_context, sources = self._compile_context(
            web_results, economic_data, news_data
        )
        logger.info("OBSERVE phase complete: %d chars context, %d sources",
                     len(raw_context), len(sources))

        # Build geographic scope hint for synthesis
        geo_scope = research_plan.get("geographic_scope", "")
        scope_location = research_plan.get("scope_location", "")
        geo_hint = ""
        if geo_scope and geo_scope != "global":
            geo_hint = f"\nGeographic scope: {geo_scope}"
            if scope_location:
                geo_hint += f" — {scope_location}"
            geo_hint += (
                "\nScope ALL analysis (TAM/SAM/SOM, competitors, overview) "
                "to this geographic area. Do NOT report global market figures."
            )

        # 4. REFLECT — Synthesize via Claude
        logger.info("REFLECT phase starting — synthesizing findings")
        synthesis = await self._synthesize(
            prompt, raw_context, skill_context, geo_hint
        )
        logger.info("REFLECT phase complete")

        return MarketResearchResponse(
            query=prompt,
            market_overview=synthesis.get("overview", ""),
            market_sizing=synthesis.get("sizing", {}),
            competitive_landscape=synthesis.get("competitors", []),
            industry_trends=synthesis.get("trends", []),
            economic_indicators=self._format_economic_data(economic_data),
            sources=sources,
            findings=synthesis.get("findings", []),
            recommendations=synthesis.get("recommendations", []),
            raw_context=raw_context[:50000],  # Limit raw context size
            confidence_score=float(synthesis.get("confidence", 0.5)),
            methodology_notes=synthesis.get("methodology", []),
        )

    async def close(self) -> None:
        """Clean up resources."""
        if self._anthropic_client is not None:
            await self._anthropic_client.close()
            self._anthropic_client = None

    # ── PLAN phase ──

    async def _plan_research(
        self, prompt: str, skill_context: str = ""
    ) -> dict[str, Any]:
        """Use Claude to decompose the research query into sub-tasks."""
        default_plan = {
            "search_queries": [prompt],
            "indicators": ["gdp", "gdp_growth"],
            "news_queries": [prompt],
            "countries": ["WLD"],
            "focus_areas": ["market_overview"],
        }

        client = self._get_anthropic()
        if client is None:
            logger.info("No Anthropic key — using default research plan")
            return default_plan

        try:
            system = _PLAN_SYSTEM_PROMPT
            if skill_context:
                system += f"\n\nAdditional context:\n{skill_context[:2000]}"

            logger.info("Calling Claude (%s) for research plan...", self.model)
            message = await client.messages.create(
                model=self.model,
                max_tokens=1024,
                temperature=self.temperature,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            logger.info("Claude plan response received")

            content = message.content[0].text.strip()
            # Extract JSON from response (handle markdown code blocks)
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()

            plan = json.loads(content)
            logger.info("Research plan: %s", json.dumps(plan, indent=2)[:500])
            return plan
        except Exception as exc:
            logger.warning("Failed to plan research via Claude: %s", exc)
            return default_plan

    # ── ACT phase ──

    async def _gather_data(
        self,
        plan: dict[str, Any],
        previous_outputs: dict[str, Any],
    ) -> tuple[list[dict], dict[str, list[dict]], list[dict]]:
        """Gather data from all sources in parallel."""
        search_queries = plan.get("search_queries", [])
        indicators = plan.get("indicators", [])
        news_queries = plan.get("news_queries", [])
        countries = plan.get("countries", ["WLD"])

        # Build coroutines
        web_coro = self._search_web(search_queries)
        econ_coro = self._fetch_economic_data(indicators, countries)
        news_coro = self._fetch_news(news_queries)

        # Execute in parallel, catching individual failures
        results = await asyncio.gather(
            web_coro, econ_coro, news_coro, return_exceptions=True
        )

        web_results = results[0] if not isinstance(results[0], Exception) else []
        economic_data = results[1] if not isinstance(results[1], Exception) else {}
        news_data = results[2] if not isinstance(results[2], Exception) else []

        for i, r in enumerate(results):
            if isinstance(r, Exception):
                logger.warning("Data gathering task %d failed: %s", i, r)

        return web_results, economic_data, news_data

    async def _search_web(self, queries: list[str]) -> list[dict[str, Any]]:
        """Search web for all queries and aggregate results."""
        all_results: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        for query in queries[:4]:  # Limit to 4 queries
            results = await self.tavily_client.search(query, max_results=5)
            for r in results:
                url = r.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_results.append(r)

        return all_results

    async def _fetch_economic_data(
        self, indicators: list[str], countries: list[str]
    ) -> dict[str, list[dict[str, Any]]]:
        """Fetch economic indicators from World Bank."""
        all_data: dict[str, list[dict[str, Any]]] = {}
        for country in countries[:3]:  # Limit to 3 countries
            data = await self.world_bank_client.get_multiple_indicators(
                indicators[:5], country=country  # Limit to 5 indicators
            )
            for name, values in data.items():
                key = f"{name}_{country}"
                all_data[key] = values
        return all_data

    async def _fetch_news(self, queries: list[str]) -> list[dict[str, Any]]:
        """Fetch news articles for all queries."""
        all_articles: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        for query in queries[:2]:  # Limit to 2 queries
            articles = await self.news_client.search_news(query, max_results=5)
            for a in articles:
                url = a.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_articles.append(a)

        return all_articles

    # ── OBSERVE phase ──

    def _compile_context(
        self,
        web_results: list[dict[str, Any]],
        economic_data: dict[str, list[dict[str, Any]]],
        news_data: list[dict[str, Any]],
    ) -> tuple[str, list[SourceItem]]:
        """Compile raw data into context string and source list."""
        parts: list[str] = []
        sources: list[SourceItem] = []

        # Web results
        if web_results:
            parts.append("## Web Research Results\n")
            for r in web_results:
                title = r.get("title", "Untitled")
                url = r.get("url", "")
                content = r.get("content", r.get("snippet", ""))
                parts.append(f"### {title}\nURL: {url}\n{content}\n")
                sources.append(SourceItem(type="web", title=title, url=url))

        # Economic data
        if economic_data:
            parts.append("## Economic Indicators\n")
            for indicator_key, values in economic_data.items():
                parts.append(f"### {indicator_key}\n")
                for v in values[:5]:  # Limit displayed data points
                    parts.append(
                        f"- {v.get('country', 'N/A')} ({v.get('date', 'N/A')}): "
                        f"{v.get('value', 'N/A')} — {v.get('indicator', '')}\n"
                    )
            sources.append(
                SourceItem(
                    type="economic_data",
                    title="World Bank Open Data",
                    url="https://data.worldbank.org",
                )
            )

        # News articles
        if news_data:
            parts.append("## Recent News\n")
            for a in news_data:
                title = a.get("title", "Untitled")
                url = a.get("url", "")
                desc = a.get("description", "")
                source_name = a.get("source", "")
                parts.append(
                    f"### {title}\n" f"Source: {source_name} | URL: {url}\n{desc}\n"
                )
                sources.append(SourceItem(type="news", title=title, url=url))

        raw_context = "\n".join(parts)
        return raw_context, sources

    @staticmethod
    def _format_economic_data(data: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        """Format economic data for response."""
        formatted: dict[str, Any] = {}
        for key, values in data.items():
            if values:
                latest = values[0]  # Most recent data point
                formatted[key] = {
                    "latest_value": latest.get("value"),
                    "latest_date": latest.get("date"),
                    "country": latest.get("country"),
                    "data_points": len(values),
                }
        return formatted

    # ── REFLECT phase ──

    async def _synthesize(
        self,
        prompt: str,
        raw_context: str,
        skill_context: str = "",
        geo_hint: str = "",
    ) -> dict[str, Any]:
        """Use Claude to synthesize research findings."""
        default_synthesis = {
            "overview": f"Market research for: {prompt}",
            "sizing": {},
            "competitors": [],
            "trends": [],
            "findings": [f"Research gathered for: {prompt}"],
            "recommendations": ["Review raw data for detailed insights."],
            "confidence": 0.3,
            "methodology": ["Automated web search", "Economic indicator lookup"],
        }

        client = self._get_anthropic()
        if client is None:
            logger.info("No Anthropic key — returning default synthesis")
            return default_synthesis

        if not raw_context.strip():
            logger.warning("No raw context for synthesis")
            return default_synthesis

        try:
            system = _SYNTHESIS_SYSTEM_PROMPT
            if skill_context:
                system += f"\n\nAdditional methodology context:\n{skill_context[:2000]}"

            user_message = (
                f"Research query: {prompt}\n\n"
            )
            if geo_hint:
                user_message += f"{geo_hint}\n\n"
            user_message += f"Raw research data:\n{raw_context[:30000]}"

            logger.info("Calling Claude (%s) for synthesis (%d chars context)...",
                         self.model, len(user_message))
            message = await client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=system,
                messages=[{"role": "user", "content": user_message}],
            )
            logger.info("Claude synthesis response received")

            content = message.content[0].text.strip()
            # Extract JSON from response
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()

            synthesis = json.loads(content)
            logger.info(
                "Synthesis complete: %d findings, confidence %.2f",
                len(synthesis.get("findings", [])),
                synthesis.get("confidence", 0),
            )
            return synthesis
        except Exception as exc:
            logger.warning("Failed to synthesize via Claude: %s", exc)
            return default_synthesis
