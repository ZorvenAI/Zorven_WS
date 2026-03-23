---
name: brand-positioning-statement-generator
version: "1.0"
description: Framework-agnostic positioning generation with multi-framework candidates and scoring — clarity, differentiation, believability, memorability (maps to SKL-BPA-06)
target_agents:
  - brand_positioning
triggers:
  - "positioning statement"
  - "positioning generation"
  - "brand statement"
  - "positioning framework"
  - "positioning candidate"
priority: 10
max_tokens: 600
---

# Positioning Statement Generator

## Purpose
Generate multiple positioning statement candidates using different strategic frameworks. Score each candidate on four quality dimensions and rank them. This is the core creative skill of the Brand Positioning Agent.

## Methodology

### 1. Input Assembly
Gather inputs from all upstream BPA skills:
- **Identity Anchor** (SKL-BPA-04): brand name, mission, values, personality, guardrails
- **Competitive Map** (SKL-BPA-01): white-space zones, competitor positions, clusters
- **Audience Needs** (SKL-BPA-02): differentiators and delighters (primary positioning fuel)
- **Trend Alignment** (SKL-BPA-03): ride/resist trends
- **RAG Context** (SKL-BPA-05): prior statements, brand guidelines, messaging restrictions

### 2. Framework Selection
Generate one candidate statement per framework. Active frameworks:

| Framework | Template Pattern |
|-----------|-----------------|
| **Classic** (Ries & Trout) | For [target audience] who [need], [brand] is the [category] that [key benefit] because [reason to believe] |
| **Blue Ocean** | [Brand] creates [new category/market space] by [eliminating/reducing/raising/creating] |
| **Jobs-to-Be-Done** | When [situation], [target] wants to [job], so they can [outcome]. [Brand] helps by [solution] |
| **Category Creation** | [Brand] is the first [new category] that [unique mechanism], unlike [old category] which [limitation] |
| **Challenger** | [Brand] challenges the belief that [industry assumption] by [counter-approach], proving [new truth] |

### 3. Candidate Count
- Default: 5 candidates (one per framework)
- Tenant-configurable via `input_context.config.bpa_candidate_count` (range 3-10)
- If configured > 5, generate additional variants of the top-scoring frameworks

### 4. Quality Scoring
Score each candidate on a 1-10 scale across four dimensions:

| Dimension | Criteria |
|-----------|----------|
| **Clarity** | Immediately understandable? Free of jargon? Single-minded? |
| **Differentiation** | Distinctly different from competitors in the map? Claims a unique space? |
| **Believability** | Supported by evidence? Aligned with brand capabilities? Not aspirational beyond credibility? |
| **Memorability** | Concise, rhythmic, quotable? Could a customer repeat it from memory? |

**Composite Score** = (Clarity * 0.25) + (Differentiation * 0.30) + (Believability * 0.25) + (Memorability * 0.20)

### 5. Constraint Validation
- Reject any candidate that violates identity guardrails from SKL-BPA-04
- Reject any candidate that uses terms from messaging restrictions (SKL-BPA-05)
- Reject any candidate that positions in a red-ocean cluster without clear differentiation (SKL-BPA-01)
- Log rejected candidates with rejection reason

### 6. Ranking and Recommendation
- Sort valid candidates by composite score descending
- Mark the top candidate as `recommended: true`
- Include a 2-3 sentence rationale for the top recommendation

## Output Schema
Write to `node_outputs.bpa_positioning_statements` with keys:
- `candidates`: list of `{framework, statement, clarity, differentiation, believability, memorability, composite_score, recommended: bool, rationale: str|null}`
- `rejected_candidates`: list of `{framework, statement, rejection_reason}`
- `candidate_count_requested`: int
- `frameworks_used`: list of str
- `top_recommendation`: `{framework, statement, composite_score, rationale}`

## Integration Notes
- SKL-BPA-07 (value proposition canvas) builds on the recommended statement
- SKL-BPA-09 (differentiation) validates PODs against the recommended statement
- SKL-BPA-10 (strategy synthesis) uses the full ranked list with rationale
