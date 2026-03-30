---
name: brand-naming-rag-retrieval
version: "1.0"
description: Retrieve prior naming documents, brand guidelines, and tagline assets from tenant RAG store for continuity with existing naming decisions (maps to SKL-NTA-05, stub v2)
target_agents:
  - naming_tagline
triggers:
  - "rag retrieval"
  - "prior naming"
  - "naming history"
  - "naming guidelines retrieval"
  - "previous names"
priority: 8
max_tokens: 400
---

# RAG Naming Retrieval

## Purpose
Query the tenant's RAG data store for prior naming documents, brand naming guidelines, trademark records, and tagline assets. This provides continuity with existing naming decisions and prevents generating names that conflict with previously rejected or approved candidates.

**Note**: This is a stub (v2 deferred). The full implementation will integrate with Vertex AI RAG. Currently, the skill checks for RAG availability and gracefully degrades when unavailable.

## Methodology

### 1. RAG Store Configuration
- Read `tenant_context.rag_data_store_id` for the Vertex AI data store identifier
- Read `tenant_context.tenant_id` for scoping queries to the correct tenant
- If `rag_data_store_id` is absent or empty, skip retrieval and set `rag_available: false`

### 2. Query Construction (v2)
When RAG is available, issue up to 5 targeted queries using the brand name from `input_context.company`:
1. **Prior Names**: `"{brand_name} brand naming candidates approved rejected"`
2. **Naming Guidelines**: `"{brand_name} naming conventions brand guidelines"`
3. **Trademark Records**: `"{brand_name} trademark registration naming conflicts"`
4. **Tagline History**: `"{brand_name} tagline slogan brand messaging"`
5. **Naming Brief**: `"{brand_name} naming brief creative brief naming strategy"`

### 3. Relevance Filtering (v2)
- Discard chunks with relevance score < 0.5
- Deduplicate overlapping chunks (> 70% content similarity)
- Cap at 10 most relevant chunks total across all queries
- Flag documents older than 24 months as potentially outdated

### 4. Prior Naming Extraction (v2)
From relevant chunks, extract structured elements:
- Previously approved brand names and taglines
- Previously rejected candidates with rejection reasons
- Naming guidelines and constraints from brand books
- Trademark clearance records
- Naming evolution history (rebranding timeline)

### 5. Stub Behavior (v1)
In the current version, always return:
- `rag_available: false`
- Empty prior naming data
- A note indicating RAG integration is deferred to v2

## Output Schema
Write to `node_outputs.nta_rag_context` with keys:
- `rag_available`: bool (always false in v1)
- `prior_approved_names`: list (empty in v1, v2: previously approved names)
- `prior_rejected_names`: list (empty in v1, v2: previously rejected names with reasons)
- `prior_taglines`: list (empty in v1, v2: previously approved taglines)
- `naming_guidelines`: list (empty in v1, v2: brand book naming rules)
- `trademark_records`: list (empty in v1, v2: clearance history)
- `staleness_warnings`: list (empty in v1)
- `total_chunks_retrieved`: 0
- `version_note`: "RAG retrieval deferred to v2 — operating without historical naming context"

## Integration Notes
- When `rag_available` is false, SKL-NTA-09 (name generator) operates without historical anchoring
- Future pipeline runs will use this skill to find naming artifacts archived by SKL-NTA-13 (persister)
- v2 implementation will follow the same pattern as BPV's SKL-BPV-04 (brand-personality-rag-retrieval)
- The stub ensures the skill contract is stable for downstream consumers before RAG is wired
