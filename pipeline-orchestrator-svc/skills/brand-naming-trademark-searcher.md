---
name: brand-naming-trademark-searcher
version: "1.0"
description: Perform Tavily web search for trademark conflicts, existing registrations, and legal risks for name candidates (maps to SKL-NTA-08)
target_agents:
  - naming_tagline
triggers:
  - "trademark search"
  - "trademark check"
  - "legal clearance"
  - "trademark conflicts"
  - "name clearance"
priority: 9
max_tokens: 500
---

# Trademark Conflict Searcher

## Purpose
Search for potential trademark conflicts for each name candidate using Tavily web search. Trademark infringement is the highest-severity naming risk — a name that infringes an existing mark can result in costly legal action and forced rebranding. This skill provides an initial screening, not a legal opinion.

## Methodology

### 1. Candidate Collection
- Read `node_outputs.nta_name_candidates` from SKL-NTA-09 for the list of name candidates
- Read `input_context.company.industry` for the relevant Nice Classification classes

### 2. Search Strategy
For each candidate, execute up to 3 Tavily web searches:
1. **USPTO Search**: `"{candidate_name}" trademark registration USPTO`
2. **General Trademark**: `"{candidate_name}" trademark registered brand`
3. **Industry-Specific**: `"{candidate_name}" {industry} brand company`

### 3. Conflict Classification
Analyze search results and classify findings:

| Conflict Type | Severity | Criteria |
|---|---|---|
| Exact match in same class | Critical | Identical name registered in the same Nice class |
| Exact match in different class | Warning | Identical name registered but in a different industry |
| Phonetically similar in same class | Warning | Name sounds alike (e.g., "Lyft" vs "Lift") |
| Visually similar in same class | Advisory | Name looks alike when written |
| Common word, no trademark | Clear | Generic/descriptive term with no specific registration found |
| No results found | Likely Clear | No evidence of existing use (best-effort) |

### 4. Nice Classification Mapping
Map the brand's industry to relevant Nice Classification classes:
- Technology: Classes 9, 35, 42
- Retail/E-commerce: Classes 35, 25, 18
- Food & Beverage: Classes 29, 30, 32, 43
- Healthcare: Classes 5, 10, 44
- Financial Services: Classes 36
- Media/Entertainment: Classes 41, 38
- Use industry mapping to assess same-class vs. different-class conflicts

### 5. Risk Score Computation (0-100)
For each candidate, compute a trademark risk score (higher = riskier):
- **Critical conflict found**: 80-100 (near-certain infringement risk)
- **Warning conflicts found**: 40-79 (potential issues requiring legal review)
- **Advisory conflicts only**: 10-39 (low risk but worth noting)
- **No conflicts found**: 0-9 (appears clear based on web search)

### 6. Disclaimer
Always include: "This trademark screening is based on web search results and is NOT a substitute for a formal trademark clearance conducted by a qualified intellectual property attorney. Engage legal counsel before finalizing any brand name."

## Output Schema
Write to `node_outputs.nta_trademark_check` with keys:
- `trademark_results`: list of `{candidate_name, conflicts: [{conflict_type, severity, source_url, existing_owner, nice_class, description}], risk_score: int, recommendation: "clear"|"review_needed"|"high_risk"}`
- `summary`: `{candidates_checked: int, clear: int, review_needed: int, high_risk: int}`
- `nice_classes_checked`: list of int
- `search_method`: "tavily_web_search"
- `disclaimer`: str

## Integration Notes
- Downstream consumers: SKL-NTA-10 (name scorer uses risk_score inversely — high risk = low score), SKL-NTA-14 (human escalation flags high-risk candidates)
- Trademark search runs concurrently with SKL-NTA-06 and SKL-NTA-07 for pipeline efficiency
- Critical trademark conflicts should be surfaced prominently in the naming brief (SKL-NTA-12)
- This is a preliminary screening — the naming brief must recommend formal legal clearance
