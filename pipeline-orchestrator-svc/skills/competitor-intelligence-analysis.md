---
name: competitor-intelligence-analysis
version: "1.0"
description: Core competitive intelligence methodology — competitor identification, SWOT framework, benchmarking report structure (maps to SKL-CIA-08, SKL-CIA-09, SKL-CIA-10)
target_agents:
  - competitor_intelligence
triggers:
  - "competitor"
  - "SWOT"
  - "competitive"
  - "benchmarking"
  - "intelligence"
  - "audit"
priority: 10
max_tokens: 500
---

## Competitive Intelligence Analysis Framework

### Competitor Identification
- Cast a wide net: direct competitors, indirect competitors, emerging disruptors
- Classify by type: **Direct** (same product/market), **Indirect** (different product, same need), **Aspirational** (where you want to be)
- Use multiple discovery signals: web search, industry reports, review sites, social media presence

### SWOT Analysis Methodology
For each competitor, generate a grounded SWOT:
- **Strengths**: Observable advantages — market share, product features, brand recognition, funding, team size
- **Weaknesses**: Documented gaps — negative reviews, missing features, pricing complaints, slow support
- **Opportunities**: Market gaps the competitor could exploit — emerging segments, geographic expansion, partnerships
- **Threats**: External risks — regulatory changes, new entrants, technology shifts, economic headwinds

Every SWOT claim MUST cite at least one source URL. Do not generate speculative SWOT items without evidence.

### Benchmarking Report Structure
1. **Executive Summary** — 2-3 paragraphs with key takeaways
2. **Competitor Matrix** — Comparative table across 6-8 dimensions
3. **Individual Competitor Profiles** — Deep-dive per competitor
4. **Positioning Gap Analysis** — Opportunities and white space
5. **Strategic Recommendations** — Actionable next steps ranked by impact

### Evidence Standards
- All claims must reference source URLs
- Distinguish between verified data and estimates
- Flag data freshness (when was the source last updated?)
- Confidence scoring: 0.8+ for well-sourced, 0.5-0.8 for partial data, <0.5 for estimates
