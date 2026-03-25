---
name: brand-personality-rag-retrieval
version: "1.0"
description: Retrieve prior personality documents, brand guidelines, and tone-of-voice assets from tenant RAG store for continuity with existing personality decisions (maps to SKL-BPV-04, stub v2)
target_agents:
  - brand_personality
triggers:
  - "rag retrieval"
  - "prior personality"
  - "personality history"
  - "brand guidelines retrieval"
  - "previous personality"
priority: 8
max_tokens: 400
---

# RAG Personality Retrieval

## Purpose
Query the tenant's RAG data store for prior brand personality documents, tone-of-voice guidelines, and character briefs. This provides continuity with existing personality decisions and prevents contradictory recommendations across pipeline re-executions.

**Note**: This is a stub (v2 deferred). The full implementation will integrate with Vertex AI RAG. Currently, the skill checks for RAG availability and gracefully degrades when unavailable.

## Methodology

### 1. RAG Store Configuration
- Read `tenant_context.rag_data_store_id` for the Vertex AI data store identifier
- Read `tenant_context.tenant_id` for scoping queries to the correct tenant
- If `rag_data_store_id` is absent or empty, skip retrieval and set `rag_available: false`

### 2. Query Construction (v2)
When RAG is available, issue up to 4 targeted queries using the brand name from `input_context.company`:
1. **Prior Personality**: `"{brand_name} brand personality profile aaker dimensions"`
2. **Voice Guidelines**: `"{brand_name} tone of voice brand voice guidelines"`
3. **Character Brief**: `"{brand_name} brand character brief archetype"`
4. **Values Documentation**: `"{brand_name} brand values hierarchy core values"`

### 3. Relevance Filtering (v2)
- Discard chunks with relevance score < 0.5
- Deduplicate overlapping chunks (> 70% content similarity)
- Cap at 10 most relevant chunks total across all queries
- Flag documents older than 18 months as potentially outdated

### 4. Prior Personality Extraction (v2)
From relevant chunks, extract structured elements:
- Previous Aaker dimension scores
- Historical archetype selection and rationale
- Existing tone-of-voice rules
- Values hierarchy from prior brand guidelines
- Personality evolution notes or rebranding history
- Personality constraints or prohibitions

### 5. Stub Behavior (v1)
In the current version, always return:
- `rag_available: false`
- Empty prior personality data
- A note indicating RAG integration is deferred to v2

## Output Schema
Write to `node_outputs.bpv_rag_context` with keys:
- `rag_available`: bool (always false in v1)
- `prior_personality_profile`: null (v2: Aaker scores from prior execution)
- `prior_archetype`: null (v2: previously selected archetype)
- `voice_guidelines`: list (empty in v1, v2: prior tone-of-voice rules)
- `values_history`: list (empty in v1, v2: prior values hierarchies)
- `personality_constraints`: list (empty in v1, v2: constraints from brand guidelines)
- `staleness_warnings`: list (empty in v1)
- `total_chunks_retrieved`: 0
- `version_note`: "RAG retrieval deferred to v2 — operating without historical personality context"

## Integration Notes
- When `rag_available` is false, SKL-BPV-05 (Aaker profiler) operates without historical anchoring
- Future pipeline runs will use this skill to find personality profiles archived by SKL-BPV-11 (persister)
- v2 implementation will follow the same pattern as BAA's SKL-BAA-05 (brand-architecture-rag-retrieval)
- The stub ensures the skill contract is stable for downstream consumers before RAG is wired
