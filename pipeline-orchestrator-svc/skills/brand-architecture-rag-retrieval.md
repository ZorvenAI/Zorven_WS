---
name: brand-architecture-rag-retrieval
version: "1.0"
description: Retrieve prior architecture documents from tenant RAG store — historical architecture decisions, brand guidelines, portfolio strategies (maps to SKL-BAA-05)
target_agents:
  - brand_architecture
triggers:
  - "prior architecture"
  - "architecture history"
  - "rag retrieval"
  - "historical architecture"
  - "previous architecture"
priority: 8
max_tokens: 400
---

# RAG Architecture Retrieval

## Purpose
Query the tenant's RAG data store for prior brand architecture documents, portfolio strategy records, and brand hierarchy guidelines. This provides continuity with existing architecture decisions and prevents contradictory structural recommendations.

## Methodology

### 1. RAG Store Configuration
- Read `tenant_context.rag_data_store_id` for the Vertex AI data store identifier
- Read `tenant_context.tenant_id` for scoping queries to the correct tenant
- If `rag_data_store_id` is absent or empty, skip retrieval and set `rag_available: false`

### 2. Query Construction
Issue up to 4 targeted RAG queries using the brand name from `input_context.company`:
1. **Prior Architecture**: `"{brand_name} brand architecture portfolio structure"`
2. **Brand Hierarchy**: `"{brand_name} brand hierarchy sub-brands product lines"`
3. **Naming Conventions**: `"{brand_name} naming conventions brand naming guidelines"`
4. **Portfolio Strategy**: `"{brand_name} portfolio growth strategy brand extension"`

### 3. Relevance Filtering
- For each returned chunk, compute a relevance score against the current architecture task
- Discard chunks with relevance score < 0.5
- Deduplicate overlapping chunks (> 70% content similarity)
- Cap at 12 most relevant chunks total across all queries

### 4. Temporal Ordering
- Extract document dates where available (upload date, document metadata, content date references)
- Sort retained chunks by recency
- Flag documents older than 24 months as potentially outdated
- Architecture documents older than 36 months are marked as "historical reference only"

### 5. Prior Architecture Extraction
From relevant chunks, extract structured elements:
- Previous architecture model decisions and rationale
- Historical brand hierarchy diagrams or descriptions
- Naming conventions and naming rules
- Portfolio growth plans and extension strategies
- Architecture constraints or prohibitions (e.g., "never use the parent brand on value-tier products")
- Past architecture failures or lessons learned

## Output Schema
Write to `node_outputs.baa_rag_context` with keys:
- `rag_available`: bool
- `prior_architecture_model`: str or null (last known architecture model)
- `prior_hierarchy`: list of `{brand_name, relationship, tier, source_file, date}`
- `naming_guidelines`: list of `{guideline, source_file, category}`
- `architecture_constraints`: list of `{constraint, source_file, rationale}`
- `growth_plans`: list of `{plan_description, source_file, date, status}`
- `lessons_learned`: list of `{lesson, context, source_file}`
- `staleness_warnings`: list of `{source_file, age_months, recommendation}`
- `total_chunks_retrieved`: int
- `total_chunks_filtered`: int

## Integration Notes
- If prior architecture exists, SKL-BAA-06 (model recommender) should evaluate continuity with the prior model
- Architecture constraints from RAG are hard constraints for SKL-BAA-07 (hierarchy builder) and SKL-BAA-08 (naming designer)
- SKL-BAA-10 (strategy synthesis) references prior architecture in its evolution narrative
- Future pipeline runs use this skill to find architecture strategies archived by SKL-BAA-11
