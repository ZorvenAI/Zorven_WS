---
name: brand-naming-name-scorer
version: "1.0"
description: Multi-dimensional scoring framework for name candidates across strategic fit, linguistic quality, practical viability, and legal safety (maps to SKL-NTA-10)
target_agents:
  - naming_tagline
triggers:
  - "name scorer"
  - "scoring framework"
  - "name evaluation"
  - "candidate ranking"
  - "name assessment"
priority: 9
max_tokens: 600
---

# Name Candidate Scorer

## Purpose
Apply a multi-dimensional scoring framework to all name candidates, incorporating strategic alignment, linguistic quality, audience resonance, practical viability (domain/handle), and legal safety (trademark). This produces a ranked shortlist with transparent scoring rationale for each candidate.

## Methodology

### 1. Input Collection
- Read SKL-NTA-09 `nta_name_candidates`: Name candidates with rationale (required)
- Read SKL-NTA-01 `nta_brand_context`: Architecture constraints for compliance scoring
- Read SKL-NTA-02 `nta_audience_psychology`: Audience preferences for resonance scoring
- Read SKL-NTA-03 `nta_competitive_naming`: Competitive landscape for differentiation scoring
- Read SKL-NTA-04 `nta_identity_seed`: Personality profile for alignment scoring
- Read SKL-NTA-06 `nta_domain_check`: Domain viability scores
- Read SKL-NTA-07 `nta_social_handles`: Social handle viability scores
- Read SKL-NTA-08 `nta_trademark_check`: Trademark risk scores

### 2. Scoring Dimensions (0-100 each)

**Strategic Fit (Weight: 25%)**:
- Architecture compliance: Does the name follow the naming convention rules? (0 or 100, binary)
- Positioning alignment: Does the name evoke the intended differentiators? (0-100)
- Values congruence: Is the name consistent with core brand values? (0-100)
- Category fit: Does the name work in the brand's industry context? (0-100)

**Linguistic Quality (Weight: 20%)**:
- Pronounceability: Easy to say in target market languages (0-100)
- Memorability: Distinctive, short, rhythmic, or phonetically pleasing (0-100)
- Spellability: Easy to spell from hearing, no ambiguous spellings (0-100)
- Cross-language safety: No negative meanings in major languages (0-100)

**Audience Resonance (Weight: 20%)**:
- Tone match: Aligns with audience's preferred communication style (0-100)
- Emotional evocation: Triggers the intended emotional associations (0-100)
- Vocabulary alignment: Matches audience's vocabulary level and preferences (0-100)
- Cultural sensitivity: No cultural, religious, or demographic offense risk (0-100)

**Practical Viability (Weight: 20%)**:
- Domain availability: Score from SKL-NTA-06 (0-100)
- Social handle availability: Score from SKL-NTA-07 (0-100)
- Visual identity potential: How well the name lends itself to logo/visual design (0-100)
- Scalability: Can the name accommodate brand extensions? (0-100)

**Legal Safety (Weight: 15%)**:
- Trademark risk: Inverse of SKL-NTA-08 risk score (0-100, where 100 = safest)
- Descriptiveness risk: Is the name too generic to trademark? (0-100)
- Prior rejection: Was this name previously rejected? (from SKL-NTA-05, 0 or 100)

### 3. Composite Score Computation
For each candidate:
- Compute weighted composite score: `strategic(25%) + linguistic(20%) + resonance(20%) + viability(20%) + legal(15%)`
- Apply architecture compliance as a hard gate: if architecture compliance = 0, cap composite at 30
- Apply trademark critical flag: if trademark risk_score > 80, cap composite at 40

### 4. Ranking and Shortlisting
- Rank all candidates by composite score (descending)
- Designate top 3 as "recommended" tier
- Designate next 3-5 as "viable" tier
- Designate remaining as "reserve" tier
- Flag any candidates with composite < 40 as "not recommended"

### 5. Scoring Rationale
For each candidate, generate a brief rationale:
- Top strength: The highest-scoring dimension and why
- Key concern: The lowest-scoring dimension and why
- Overall assessment: One-sentence verdict

## Output Schema
Write to `node_outputs.nta_name_scores` with keys:
- `scored_candidates`: list of `{name, composite_score: int, tier: "recommended"|"viable"|"reserve"|"not_recommended", dimension_scores: {strategic: int, linguistic: int, resonance: int, viability: int, legal: int}, dimension_breakdown: {}, top_strength: str, key_concern: str, rationale: str}`
- `ranking`: list of `{rank: int, name: str, composite_score: int, tier: str}`
- `scoring_weights`: `{strategic: 0.25, linguistic: 0.20, resonance: 0.20, viability: 0.20, legal: 0.15}`
- `score_distribution`: `{mean: float, median: float, std_dev: float, highest: int, lowest: int}`

## Integration Notes
- Downstream consumers: SKL-NTA-11 (tagline synthesizer focuses on recommended-tier names), SKL-NTA-12 (naming brief presents ranked results), SKL-NTA-14 (escalation flags low overall scores)
- Architecture compliance hard gate ensures non-compliant names cannot rank highly regardless of other strengths
- Scoring transparency is critical — every score must be traceable to a specific input or assessment
