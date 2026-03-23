---
name: brand-positioning-rag-retrieval
version: "1.0"
description: Retrieve prior positioning strategies and brand guidelines from tenant RAG store (maps to SKL-BPA-05)
target_agents:
  - brand_positioning
triggers:
  - "prior positioning"
  - "brand guidelines"
  - "rag retrieval"
  - "historical strategy"
  - "previous positioning"
priority: 8
max_tokens: 400
---

# RAG Positioning Retrieval

## Purpose
Query the tenant's RAG data store for prior positioning strategies, brand guidelines, and historical brand documents. This provides continuity with existing brand work and prevents contradictory positioning recommendations.

## Methodology

### 1. RAG Store Configuration
- Read `tenant_context.rag_data_store_id` for the Vertex AI data store identifier
- Read `tenant_context.tenant_id` for scoping queries to the correct tenant
- If `rag_data_store_id` is absent or empty, skip retrieval and set `rag_available: false`

### 2. Query Construction
Issue up to 3 targeted RAG queries using the brand name from `input_context.company`:
1. **Prior Positioning**: `"{brand_name} positioning statement strategy"`
2. **Brand Guidelines**: `"{brand_name} brand guidelines identity standards"`
3. **Competitive Context**: `"{brand_name} competitive differentiation unique value"`

### 3. Relevance Filtering
- For each returned chunk, compute a relevance score against the current positioning task
- Discard chunks with relevance score < 0.5
- Deduplicate overlapping chunks (> 70% content similarity)
- Cap at 10 most relevant chunks total across all queries

### 4. Temporal Ordering
- Extract document dates where available (upload date, document metadata, content date references)
- Sort retained chunks by recency
- Flag documents older than 24 months as potentially outdated

### 5. Prior Strategy Extraction
From relevant chunks, extract structured elements:
- Previous positioning statements (verbatim if found)
- Historical value propositions
- Brand voice and tone guidelines
- Do-not-use terms or messaging restrictions
- Competitive claims made in prior materials

## Output Schema
Write to `node_outputs.bpa_rag_context` with keys:
- `rag_available`: bool
- `prior_statements`: list of `{text, source_file, date, relevance_score}`
- `brand_guidelines`: list of `{guideline, source_file, category}`
- `messaging_restrictions`: list of `{restriction, source_file}`
- `historical_competitors_mentioned`: list of str
- `staleness_warnings`: list of `{source_file, age_months, recommendation}`
- `total_chunks_retrieved`: int
- `total_chunks_filtered`: int

## Integration Notes
- If prior positioning exists, SKL-BPA-06 (statement generator) should evaluate whether to evolve or replace it
- Messaging restrictions from brand guidelines are hard constraints for all downstream skills
- SKL-BPA-10 (strategy synthesis) references prior strategies in its evolution narrative
