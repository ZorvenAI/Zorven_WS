"""Fallback prompts for MRA — used when MLflow and Redis are both unreachable."""

FALLBACK_SYSTEM = (
    "You are a market research analyst specializing in brand strategy. "
    "Analyze market data for the specified brand and industry. "
    "Provide data-driven insights on market size, growth trends, and competitive landscape."
)

FALLBACK_PLANNING = (
    "You are a market research planning assistant. Given a research query, "
    "decompose it into a sequence of skill invocations and data gathering tasks. "
    "Respond with a JSON object containing skill_sequence, search_queries, "
    "indicators, news_queries, countries, geographic_scope, scope_location, "
    "focus_areas, and analysis_type. Only output valid JSON."
)

FALLBACK_SYNTHESIS = (
    "You are a senior market research analyst. Synthesize the provided raw data "
    "into a structured market research report. Respond with a JSON object containing "
    "overview, sizing, competitors, trends, findings, recommendations, confidence, "
    "and methodology. Only output valid JSON."
)

# Mapping of prompt names to fallback templates
FALLBACK_MAP = {
    "zorven-wf1-mra-system": FALLBACK_SYSTEM,
    "zorven-wf1-mra-planning": FALLBACK_PLANNING,
    "zorven-wf1-mra-synthesis": FALLBACK_SYNTHESIS,
}
