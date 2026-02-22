"""
Competitive gap analysis from discovery research findings.

Identifies competitor strengths, weaknesses, and market gaps.
Uses Gemini AI for rich analysis when available, falls back to
keyword-based rule extraction.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Keywords indicating competitive strengths
STRENGTH_KEYWORDS = [
    "leading", "dominant", "strong", "innovative", "growth",
    "market leader", "premium", "established", "trusted",
]

# Keywords indicating competitive weaknesses or gaps
GAP_KEYWORDS = [
    "gap", "weakness", "lacking", "behind", "trailing",
    "underperforming", "limited", "missing", "opportunity",
    "decline", "erosion", "vulnerable",
]


class CompetitiveGapAnalyzer:
    """Identifies competitive gaps from discovery research findings."""

    async def analyze(
        self,
        previous_outputs: dict[str, Any],
        config: dict[str, Any],
        gemini_client: Any | None = None,
    ) -> dict[str, Any]:
        """
        Extract competitor strengths/weaknesses from discovery findings.

        Args:
            previous_outputs: Outputs from upstream nodes (discovery findings).
            config: Analysis configuration.
            gemini_client: Optional Gemini client for AI analysis.

        Returns:
            Dict with strengths, weaknesses, gaps, and market_opportunities.
        """
        discovery_data = self._extract_discovery_data(previous_outputs)

        if not discovery_data:
            logger.warning("No discovery data found for gap analysis")
            return {
                "strengths": [],
                "weaknesses": [],
                "gaps": ["Insufficient discovery data for gap analysis."],
                "market_opportunities": [],
            }

        if gemini_client:
            return await self._ai_analysis(discovery_data, config, gemini_client)
        return self._rule_based_analysis(discovery_data)

    def _extract_discovery_data(
        self, previous_outputs: dict[str, Any]
    ) -> list[str]:
        """Extract findings from all upstream discovery nodes."""
        all_findings: list[str] = []
        for node_id, output in previous_outputs.items():
            if isinstance(output, dict):
                findings = output.get("findings", [])
                if isinstance(findings, list):
                    all_findings.extend(str(f) for f in findings)
                raw_context = output.get("raw_context", "")
                if raw_context and isinstance(raw_context, str):
                    # Split raw context into paragraphs for analysis
                    paragraphs = [
                        p.strip()
                        for p in raw_context.split("\n\n")
                        if p.strip() and len(p.strip()) > 20
                    ]
                    all_findings.extend(paragraphs[:10])
        return all_findings

    def _rule_based_analysis(
        self, findings: list[str]
    ) -> dict[str, Any]:
        """Keyword-based competitive gap extraction."""
        strengths: list[str] = []
        weaknesses: list[str] = []
        gaps: list[str] = []

        for finding in findings:
            finding_lower = finding.lower()

            has_strength = any(kw in finding_lower for kw in STRENGTH_KEYWORDS)
            has_gap = any(kw in finding_lower for kw in GAP_KEYWORDS)

            if has_gap:
                gaps.append(finding)
            elif has_strength:
                strengths.append(finding)
            else:
                weaknesses.append(finding)

        # Generate market opportunities from gaps
        market_opportunities = []
        if gaps:
            market_opportunities.append(
                f"Address {len(gaps)} identified competitive gaps to strengthen market position."
            )
        if not strengths:
            market_opportunities.append(
                "Build stronger brand positioning through differentiated offerings."
            )

        logger.info(
            "Gap analysis: %d strengths, %d weaknesses, %d gaps",
            len(strengths),
            len(weaknesses),
            len(gaps),
        )

        return {
            "strengths": strengths,
            "weaknesses": weaknesses,
            "gaps": gaps or ["No significant competitive gaps identified."],
            "market_opportunities": market_opportunities or [
                "Continue monitoring competitive landscape."
            ],
        }

    async def _ai_analysis(
        self,
        findings: list[str],
        config: dict[str, Any],
        gemini_client: Any,
    ) -> dict[str, Any]:
        """AI-powered competitive gap analysis using Gemini."""
        try:
            findings_text = "\n".join(f"- {f}" for f in findings[:20])
            prompt = (
                "Analyze the following market research findings and identify:\n"
                "1. Competitor strengths (list)\n"
                "2. Competitor weaknesses (list)\n"
                "3. Competitive gaps and opportunities (list)\n"
                "4. Market opportunities for differentiation (list)\n\n"
                f"Findings:\n{findings_text}\n\n"
                "Return a structured analysis with clear, actionable items."
            )

            model_name = config.get("model", "gemini-2.0-flash")
            model = gemini_client.GenerativeModel(model_name)
            response = await model.generate_content_async(prompt)
            text = response.text

            # Parse AI response into structured format
            return self._parse_ai_response(text, findings)
        except Exception as exc:
            logger.warning("Gemini analysis failed, falling back to rules: %s", exc)
            return self._rule_based_analysis(findings)

    def _parse_ai_response(
        self, text: str, original_findings: list[str]
    ) -> dict[str, Any]:
        """Parse Gemini response into structured gap analysis."""
        lines = [line.strip() for line in text.split("\n") if line.strip()]

        # Simple section-based parsing
        sections: dict[str, list[str]] = {
            "strengths": [],
            "weaknesses": [],
            "gaps": [],
            "market_opportunities": [],
        }
        current_section = "gaps"

        for line in lines:
            line_lower = line.lower()
            if "strength" in line_lower:
                current_section = "strengths"
                continue
            elif "weakness" in line_lower:
                current_section = "weaknesses"
                continue
            elif "gap" in line_lower or "opportunit" in line_lower:
                if "market" in line_lower:
                    current_section = "market_opportunities"
                else:
                    current_section = "gaps"
                continue

            # Add bullet points to current section
            cleaned = line.lstrip("-*• ").strip()
            if cleaned and len(cleaned) > 5:
                sections[current_section].append(cleaned)

        # Ensure non-empty results
        for key in sections:
            if not sections[key]:
                fallback = self._rule_based_analysis(original_findings)
                sections[key] = fallback.get(key, [])

        return sections
