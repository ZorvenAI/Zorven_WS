---
name: brand-naming-naming-brief
version: "1.0"
description: Compile the final naming brief document synthesizing all naming analysis, scored candidates, taglines, availability checks, and actionable recommendations (maps to SKL-NTA-12)
target_agents:
  - naming_tagline
triggers:
  - "naming brief"
  - "naming document"
  - "naming report"
  - "naming deliverable"
  - "final brief"
priority: 8
max_tokens: 600
---

# Naming Brief Compiler

## Purpose
Synthesize all upstream NTA skill outputs into a comprehensive naming brief document — the primary deliverable of the Naming & Tagline Agent. This brief provides stakeholders with ranked name recommendations, paired taglines, availability assessments, risk analysis, and clear next steps.

## Methodology

### 1. Input Collection
Collect all upstream skill outputs:
- SKL-NTA-01 `nta_brand_context`: Architecture and positioning context
- SKL-NTA-02 `nta_audience_psychology`: Audience preferences summary
- SKL-NTA-03 `nta_competitive_naming`: Competitive landscape summary
- SKL-NTA-04 `nta_identity_seed`: Personality and values alignment
- SKL-NTA-05 `nta_rag_context`: Prior naming history
- SKL-NTA-06 `nta_domain_check`: Domain availability results
- SKL-NTA-07 `nta_social_handles`: Social handle availability results
- SKL-NTA-08 `nta_trademark_check`: Trademark risk results
- SKL-NTA-09 `nta_name_candidates`: Generated name candidates
- SKL-NTA-10 `nta_name_scores`: Scored and ranked candidates
- SKL-NTA-11 `nta_taglines`: Tagline pairings

### 2. Executive Summary
Compile a concise executive summary (3-5 sentences):
- Brand context and naming objective
- Number of candidates evaluated
- Top recommendation with rationale
- Key risk or concern (if any)
- Overall confidence level

### 3. Recommended Names Section
For each recommended-tier name (top 3), present:
- **Name**: The candidate name
- **Composite Score**: Overall score with dimension breakdown
- **Tagline Pairing**: Best-matched tagline with pairing score
- **Domain**: Recommended domain and alternatives
- **Social Handles**: Availability summary across platforms
- **Trademark Status**: Risk level and any flagged conflicts
- **Rationale**: Why this name is recommended (strategic fit, linguistic quality, practical viability)
- **Concerns**: Any noted risks or trade-offs

### 4. Viable Alternatives Section
For viable-tier names (ranked 4-8), present a condensed view:
- Name, composite score, best tagline, domain status, trademark status
- Brief rationale for inclusion in the viable tier

### 5. Competitive Landscape Summary
- Key competitor names and patterns
- White space the recommended names exploit
- Differentiation assessment

### 6. Availability Dashboard
Summary table:
| Name | .com Domain | Social Handles | Trademark Risk |
|---|---|---|---|
| Candidate 1 | available/taken | 5/6 platforms | clear/review/high |
| ... | ... | ... | ... |

### 7. Next Steps and Recommendations
- Formal trademark clearance for top 3 candidates (mandatory)
- Domain registration for the selected name (time-sensitive)
- Social handle reservation across platforms
- Stakeholder review session for final selection
- Legal counsel engagement timeline

### 8. Confidence Assessment
Compute overall naming brief confidence (0.0-1.0):
- `data_breadth` (0.25): How many upstream skills contributed data
- `candidate_quality` (0.25): Mean composite score of recommended tier
- `availability_strength` (0.25): Domain + social handle viability of top candidates
- `legal_safety` (0.25): Trademark clearance status of top candidates

## Output Schema
Write to `node_outputs.nta_naming_brief` with keys:
- `executive_summary`: str
- `recommended_names`: list of `{name, composite_score, tagline, domain, social_handles_summary, trademark_status, rationale, concerns}`
- `viable_alternatives`: list of `{name, composite_score, tagline, domain_status, trademark_status, brief_rationale}`
- `availability_dashboard`: list of `{name, domain_status, social_status, trademark_status}`
- `competitive_summary`: str
- `next_steps`: list of `{action, priority: "immediate"|"short_term"|"medium_term", responsible_party}`
- `confidence_score`: float (0.0-1.0)
- `confidence_breakdown`: `{data_breadth, candidate_quality, availability_strength, legal_safety}`
- `data_completeness`: `{skills_contributed: int, skills_total: int, missing_skills: []}`

## Integration Notes
- This is the primary deliverable skill — its output forms the core of the NTA result_data sent via callback to Django
- Downstream consumers: SKL-NTA-13 (persister archives the brief), SKL-NTA-14 (escalation evaluates confidence)
- The naming brief is rendered in the Django workspace UI as the NTA results panel
- Confidence < 0.5 triggers a warning in SKL-NTA-14 (human escalation)
