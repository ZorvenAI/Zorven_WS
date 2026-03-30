---
name: campaign-arch-rag-intelligence-retriever
version: "1.0"
description: Retrieve prior campaign performance learnings from RAG Intelligence Loop across audience insights, funnel optimization, budget allocation, and competitive tactics categories (maps to SKL-CAA-05)
target_agents:
  - campaign_architecture
triggers:
  - "campaign learnings"
  - "prior campaigns"
  - "rag intelligence"
  - "campaign history"
priority: 10
max_tokens: 400
---

# RAG Intelligence Retriever

## Purpose
Query the RAG Intelligence Loop for prior campaign performance data and learnings. This enables the campaign architecture to improve over successive iterations by incorporating historical performance signals.

## Methodology

### 1. RAG Availability Check
Verify RAG data store accessibility:
- Tenant context must include `rag_data_store_id`
- If no data store configured, return empty result with `rag_available: false`

### 2. Targeted Retrieval Queries
Execute 4 category-specific RAG queries using the tenant's data store:

**Audience Insights**:
- "Which audience segments performed best in prior campaigns?"
- Retrieves: top-performing demographics, interest targeting, lookalike performance

**Funnel Optimization**:
- "What funnel stage allocations produced the best ROAS?"
- Retrieves: TOFU/MOFU/BOFU split performance, conversion rate by stage

**Budget Allocation**:
- "What budget levels and distribution produced optimal results?"
- Retrieves: daily budget sweet spots, CBO vs ABO performance, placement spend distribution

**Competitive Tactics**:
- "Which competitive differentiation strategies worked in ads?"
- Retrieves: messaging angles, creative formats, positioning approaches that outperformed

### 3. Relevance Filtering
For each retrieved document:
- Score relevance (0-1) based on recency and campaign similarity
- Discard results with relevance < 0.3
- Prioritize learnings from the same industry vertical

### 4. First-Campaign Handling
For brands with no prior campaign data:
- Return empty learnings with `is_first_campaign: true`
- Downstream skills use industry benchmarks (SKL-CAA-02) as sole reference
- This is the expected case for new brands and is not an error condition

## Output Schema
Write to `node_outputs.caa_rag_intelligence` with keys:
- `rag_available`: boolean
- `is_first_campaign`: boolean
- `audience_insights`: list of `{insight, source_campaign, relevance_score}`
- `funnel_learnings`: list of `{learning, optimal_allocation, relevance_score}`
- `budget_learnings`: list of `{learning, budget_range, relevance_score}`
- `competitive_learnings`: list of `{learning, tactic, relevance_score}`
- `total_prior_campaigns`: int
- `retrieval_confidence`: float (0-1)

## Integration Notes
- Consumed by SKL-CAA-06 (funnel objective mapper) to refine allocation defaults
- Consumed by SKL-CAA-08 (placement budget builder) to optimize budget distribution
- Consumed by SKL-CAA-10 (blueprint synthesizer) for evidence-based projections
- Returns empty learnings (not an error) for first-time campaign generation
