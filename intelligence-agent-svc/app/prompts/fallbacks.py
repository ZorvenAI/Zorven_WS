"""Hardcoded fallback prompts for intelligence-agent-svc.

These are the original prompt texts extracted from the codebase before
prompt-optimization-svc integration.  They serve as Tier-3 fallbacks
when both Redis cache and MLflow are unavailable.
"""

FALLBACK_COMPANY_LOOKUP = (
    'Look up the real, publicly available financial data '
    'for "{company_name}". Provide the data as a JSON '
    'object with ONLY these keys:\n'
    '  "company_name": the official company name (string)\n'
    '  "sector": one of: technology, software, '
    'consumer_goods, retail, automotive, '
    'aerospace, defense, industrial, '
    'electric_vehicles, '
    'financial_services, media, healthcare, '
    'pharmaceuticals, luxury, energy, '
    'telecommunications (string)\n'
    '  "base_revenue": most recent annual revenue in USD '
    '(integer, e.g. 51000000000 for $51B)\n'
    '  "growth_rate": year-over-year revenue growth rate '
    'as a decimal (e.g. 0.10 for 10%)\n'
    '  "brand_awareness": estimated global brand awareness '
    'score from 0 to 100 (integer)\n'
    '  "profit_margin": net profit margin as a decimal '
    '(e.g. 0.15 for 15%)\n'
    '  "customer_loyalty": estimated customer loyalty/'
    'retention score from 0 to 100 (integer, based on '
    'repeat purchase rates, NPS, brand switching costs)\n'
    '  "market_share": estimated market share in primary '
    'market as a decimal (e.g. 0.25 for 25%)\n\n'
    'IMPORTANT: Use real data from public filings and '
    'reports. If the company is private or you cannot '
    'determine its financials, respond with exactly: '
    'NOT_FOUND\n\n'
    'Respond with ONLY the JSON object (or NOT_FOUND). '
    'No markdown fences, no explanation.'
)

FALLBACK_COMPETITIVE_GAP = (
    "Analyze the following market research findings and identify:\n"
    "1. Competitor strengths (list)\n"
    "2. Competitor weaknesses (list)\n"
    "3. Competitive gaps and opportunities (list)\n"
    "4. Market opportunities for differentiation (list)\n\n"
    "{skill_context}"
    "Findings:\n{findings_text}\n\n"
    "Return a structured analysis with clear, actionable items."
)

FALLBACK_MAP: dict[str, str] = {
    "zorven-intelligence-company-lookup": FALLBACK_COMPANY_LOOKUP,
    "zorven-intelligence-competitive-gap": FALLBACK_COMPETITIVE_GAP,
}
