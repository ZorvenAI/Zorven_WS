---
name: creative-gen-learnings-loader
version: "1.0"
description: Optional RAG search for prior creative performance learnings to inform current creative generation with historical win/loss patterns (maps to SKL-CGA-03)
target_agents:
  - creative_generation
triggers:
  - "creative learnings"
  - "prior creative performance"
  - "historical creative data"
  - "past ad performance"
priority: 10
max_tokens: 800
---

# Learnings Loader

## Purpose
Search the tenant's RAG data store for prior creative performance data, historical ad results, and previously successful creative patterns. This optional enrichment step provides data-driven guidance to downstream creative generation, helping avoid past failures and replicate past successes.

## Methodology

### 1. Construct RAG Queries
Build targeted search queries from the CGA context:
- Brand name + "ad performance" + industry
- Audience segment names + "creative results"
- Funnel stage + "conversion rate" + "click-through rate"
- Product/service category + "Meta ads" + "creative learnings"
- Competitor names + "ad creative" + "benchmark"

### 2. Execute RAG Search
Query the tenant's Vertex AI RAG data store:
- Use `tenant_context.rag_data_store_id` for store selection
- Submit 3-5 queries with relevance threshold 0.6
- Deduplicate results across queries
- Cap at 20 retrieved documents to stay within token budget

### 3. Extract Performance Patterns
From retrieved documents, identify:
- **Winning patterns**: Image styles, copy lengths, CTAs, and hooks that drove high CTR/ROAS
- **Losing patterns**: Creative approaches that underperformed benchmarks
- **Audience-specific insights**: Which creative elements resonated with which segments
- **Seasonal patterns**: Time-of-year effects on creative performance
- **Format preferences**: Image vs. video vs. carousel performance by funnel stage

### 4. Synthesize Learnings
Aggregate findings into actionable creative guidance:
- Rank patterns by confidence (number of supporting data points)
- Flag contradictions (e.g., short copy won in TOFU but lost in BOFU)
- Generate do/don't recommendations per audience-funnel combination
- Note recency of data (deprioritize learnings older than 12 months)

### 5. Graceful Degradation
If RAG data store is unavailable or returns no results:
- Log warning and continue pipeline without learnings
- Set `learnings_available` flag to false
- Downstream skills proceed with industry benchmarks only

## Output Schema
Write to `node_outputs.cga_learnings` with keys:
- `learnings_available`: boolean
- `query_count`: int
- `documents_retrieved`: int
- `winning_patterns`: list of pattern dicts with `element`, `description`, `confidence`, `data_points`
- `losing_patterns`: list of pattern dicts with same structure
- `audience_insights`: dict keyed by audience name with creative preferences
- `format_preferences`: dict keyed by funnel stage with ranked format list
- `recommendations`: list of `{audience, funnel_stage, do_list, dont_list}`
- `data_recency`: string (ISO date of most recent data point)

## Integration Notes
- This skill is optional; pipeline continues if no learnings are found
- Consumed by SKL-CGA-04 (image prompts), SKL-CGA-07 (hooks), SKL-CGA-08 (primary copy)
- Learnings influence creative generation but do not override brand guidelines
- Confidence scores from learnings feed into final package confidence in SKL-CGA-12
- Rate-limit RAG queries to avoid Vertex AI quota exhaustion
