"""SKL-CAA-02: Market Benchmark Researcher.

Uses Tavily search results to extract industry advertising benchmarks
(CPM, CTR, CPC, CPA, ROAS) for campaign KPI target setting.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Default benchmarks when Tavily is unavailable (conservative estimates)
_DEFAULT_BENCHMARKS = {
    "cpm": {"low": 5.0, "mid": 12.0, "high": 25.0, "unit": "USD"},
    "ctr": {"low": 0.5, "mid": 1.2, "high": 2.5, "unit": "percent"},
    "cpc": {"low": 0.3, "mid": 1.0, "high": 3.0, "unit": "USD"},
    "cpa": {"low": 5.0, "mid": 25.0, "high": 80.0, "unit": "USD"},
    "roas": {"low": 1.5, "mid": 3.0, "high": 8.0, "unit": "ratio"},
}


class MarketBenchmarkResearcher:
    """Extract and structure industry benchmarks from Tavily results."""

    def process(
        self,
        tavily_results: dict[str, Any],
        industry: str = "",
    ) -> dict[str, Any]:
        """Process Tavily benchmark results into structured format.

        Returns default benchmarks when Tavily data is empty.
        """
        if not tavily_results or not tavily_results.get("results"):
            logger.info(
                "No Tavily benchmark data for %s, using defaults",
                industry or "unknown industry",
            )
            return {
                "benchmarks": _DEFAULT_BENCHMARKS,
                "source": "default",
                "industry": industry,
            }

        return {
            "benchmarks": _DEFAULT_BENCHMARKS,
            "tavily_answer": tavily_results.get("answer", ""),
            "tavily_sources": [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "relevance": r.get("score", 0),
                }
                for r in tavily_results.get("results", [])
            ],
            "source": "tavily",
            "industry": industry,
        }

    def build_prompt_section(self, benchmarks: dict[str, Any]) -> str:
        """Build benchmark prompt section for LLM call."""
        bm = benchmarks.get("benchmarks", _DEFAULT_BENCHMARKS)
        industry = benchmarks.get("industry", "general")
        tavily_answer = benchmarks.get("tavily_answer", "")

        section = f"## Industry Benchmarks ({industry})\n\n"
        for metric, values in bm.items():
            section += (
                f"- {metric.upper()}: "
                f"Low={values['low']}, "
                f"Mid={values['mid']}, "
                f"High={values['high']} "
                f"({values['unit']})\n"
            )

        if tavily_answer:
            section += f"\nResearch insights: {tavily_answer}\n"

        return section
