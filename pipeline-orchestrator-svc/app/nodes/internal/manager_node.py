"""
ManagerNode — Aggregates node outputs into final result_data.

This is typically the terminal node in a pipeline. It collects
all previous node outputs and formats them for the frontend
ResultDashboard and BrandEquityDashboard components.
"""

from typing import Any

from app.nodes.base import BaseNode
from app.state.schema import AgentState

_RESEARCH_NODES = {"default_agent", "web_research"}
_MARKET_RESEARCH_NODES = {"market_research"}


def _source_label(source: dict) -> str:
    """Extract a human-readable label from a source dict.

    Different upstream nodes use different field names for the source label:
    - DefaultAgentNode (RAG):   {"name": "...", "uri": "..."}
    - discovery-agent-svc:      {"title": "...", "url": "..."}
    """
    return source.get("name") or source.get("title") or ""


class ManagerNode(BaseNode):
    """Aggregates all node outputs into a structured result."""

    async def __call__(self, state: AgentState) -> dict:
        outputs = state.get("node_outputs", {})

        findings: list[str] = []
        recommendations: list[str] = []

        # When downstream processing nodes (blog_author, social_promoter, etc.)
        # have their own findings, replace the research node's verbose
        # conversational answer with a brief source summary.  This prevents
        # contradictory messages like "I cannot schedule posts" from the RAG
        # node appearing alongside "Scheduled on: linkedin, twitter" from the
        # social promoter.  In standalone chat (research + manager only) the
        # full answer is preserved.
        processing_nodes = {nid for nid in outputs if nid not in _RESEARCH_NODES}
        has_processing = bool(processing_nodes)

        for node_id, output in outputs.items():
            if isinstance(output, dict):
                if has_processing and node_id in _RESEARCH_NODES:
                    # Summarise research sources instead of full findings
                    sources = output.get("sources", [])
                    source_names = [
                        _source_label(s) for s in sources if isinstance(s, dict)
                    ]
                    source_names = [n for n in source_names if n]
                    if source_names:
                        findings.append(
                            f"Research data retrieved from: "
                            f"{', '.join(source_names[:5])}"
                        )
                    continue
                findings.extend(output.get("findings", []))
                recommendations.extend(output.get("recommendations", []))

        # Extract BSI and valuation data from intelligence agent output
        bsi_data = self._extract_bsi(outputs)
        valuation_data = self._extract_valuation(outputs)

        # Extract market research data
        market_research_data = self._extract_market_research(outputs)

        result_data: dict[str, Any] = {
            "summary": (
                f"Pipeline analysis completed. "
                f"Processed {len(outputs)} agent(s) with results."
            ),
            "findings": findings or ["Analysis completed successfully."],
            "recommendations": recommendations
            or ["Review the detailed node outputs for actionable insights."],
            "node_results": outputs,
        }

        # Promote market research fields to top-level result_data
        if market_research_data:
            for key in (
                "market_overview",
                "market_sizing",
                "competitive_landscape",
                "industry_trends",
                "economic_indicators",
                "sources",
                "confidence_score",
                "methodology_notes",
            ):
                value = market_research_data.get(key)
                if value:
                    result_data[key] = value

        # Populate score from BSI (used by BrandEquityDashboard)
        if bsi_data:
            result_data["score"] = bsi_data.get("score", 0)
            # Extract pillar scores for dashboard gauges
            pillars = bsi_data.get("pillars", [])
            for pillar in pillars:
                if isinstance(pillar, dict):
                    name = pillar.get("name", "").lower()
                    pillar_score = pillar.get("score")
                    if pillar_score is not None:
                        if "financial" in name:
                            result_data["financials"] = pillar_score
                        elif "behavioral" in name or "awareness" in name:
                            result_data["awareness"] = pillar_score
                        elif "legal" in name:
                            # Maps ISO 10668 Legal pillar to the "sentiment"
                            # gauge on the BrandEquityDashboard frontend
                            # component for backward compatibility.
                            result_data["sentiment"] = pillar_score
        else:
            result_data["score"] = 0

        # Include valuation data if available
        if valuation_data:
            result_data["valuation"] = valuation_data

        # Generate UI schema hints when manifest-ui-mapper skill is active
        skill_context = self.config.get("skill_context", "") if self.config else ""
        if skill_context:
            result_data["ui_schema"] = self._build_ui_schema(
                outputs, bsi_data, valuation_data
            )

        return {"result_data": result_data}

    @staticmethod
    def _build_ui_schema(
        outputs: dict[str, Any],
        bsi_data: dict[str, Any] | None,
        valuation_data: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Build a UI schema object based on available pipeline results.

        Tells the frontend which charts and visualizations to render.
        """
        charts: list[dict[str, str]] = []

        # Check for market research data
        has_market_research = any(
            isinstance(o, dict) and o.get("market_sizing")
            for o in outputs.values()
        )

        # Brand equity / valuation pipeline
        if bsi_data:
            charts.append(
                {
                    "type": "radar_chart",
                    "data_key": "bsi.pillars",
                    "label": "Brand Strength Pillars",
                }
            )
            charts.append(
                {
                    "type": "score_gauge",
                    "data_key": "score",
                    "max": "100",
                    "label": "Overall BSI Score",
                }
            )
        if valuation_data:
            charts.append(
                {
                    "type": "valuation_card",
                    "data_key": "valuation.brand_value_npv",
                    "label": "Brand Value",
                }
            )

        # Content pipeline
        has_blog = any(
            isinstance(o, dict) and "blog_content" in o for o in outputs.values()
        )
        has_social = any(
            isinstance(o, dict) and "adapted_posts" in o for o in outputs.values()
        )
        if has_blog:
            charts.append({"type": "word_count_badge", "data_key": "word_count"})
            charts.append({"type": "seo_score_card", "data_key": "seo_meta"})
        if has_social:
            charts.append({"type": "platform_cards", "data_key": "adapted_posts"})

        # Determine dashboard type
        if bsi_data or valuation_data:
            schema_type = "brand_equity_dashboard"
        elif has_market_research:
            schema_type = "market_research_dashboard"
            charts.append(
                {"type": "market_sizing_cards", "data_key": "market_sizing"}
            )
            charts.append(
                {
                    "type": "competitive_landscape_table",
                    "data_key": "competitive_landscape",
                }
            )
            charts.append(
                {"type": "industry_trends_list", "data_key": "industry_trends"}
            )
            charts.append({"type": "sources_table", "data_key": "sources"})
        elif has_blog or has_social:
            schema_type = "content_dashboard"
        elif any(isinstance(o, dict) and o.get("sources") for o in outputs.values()):
            schema_type = "research_dashboard"
            charts.append({"type": "findings_list", "data_key": "findings"})
            charts.append({"type": "sources_table", "data_key": "sources"})
        else:
            schema_type = "generic_result"
            charts.append({"type": "findings_list", "data_key": "findings"})
            charts.append(
                {"type": "recommendations_list", "data_key": "recommendations"}
            )

        return {"type": schema_type, "charts": charts}

    @staticmethod
    def _extract_bsi(outputs: dict[str, Any]) -> dict[str, Any] | None:
        """Extract BSI data from any node output."""
        for node_id, output in outputs.items():
            if isinstance(output, dict):
                bsi = output.get("bsi")
                if isinstance(bsi, dict) and "score" in bsi:
                    return bsi
        return None

    @staticmethod
    def _extract_valuation(outputs: dict[str, Any]) -> dict[str, Any] | None:
        """Extract valuation data from any node output."""
        for node_id, output in outputs.items():
            if isinstance(output, dict):
                val = output.get("valuation")
                if isinstance(val, dict) and "brand_value_npv" in val:
                    return val
        return None

    @staticmethod
    def _extract_market_research(outputs: dict[str, Any]) -> dict[str, Any] | None:
        """Extract market research data from any node output.

        Looks for outputs containing market_sizing or market_overview,
        which are produced by the market-research-agent-svc.
        """
        for node_id, output in outputs.items():
            if isinstance(output, dict):
                if output.get("market_sizing") or output.get("market_overview"):
                    return output
        return None
