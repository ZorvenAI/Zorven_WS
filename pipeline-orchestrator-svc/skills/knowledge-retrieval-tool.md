---
name: knowledge-retrieval-tool
version: "1.0"
description: Vertex AI Search knowledge retrieval and tenant-scoped document lookup
target_agents:
  - default_agent
triggers:
  - "document"
  - "file"
  - "upload"
  - "knowledge"
  - "search"
  - "find"
  - "look up"
  - "rag"
  - "onboard"
  - "attached"
priority: 10
max_tokens: 400
---
# KnowledgeRetrievalTool — Vertex AI Search Integration

## Purpose
Interface with tenant-scoped Vertex AI Search indices to retrieve
relevant document chunks for grounded, source-cited answers.

## Tenant-to-Data-Store Mapping
- Map tenant_id to the specific Vertex AI Data Store ID
- Use tenant_context.rag_data_store_id when provided (override)
- Fall back to the default data store when no override is set
- Data store path format: projects/{project}/locations/{location}/collections/default_collection/dataStores/{store_id}

## Search Strategy
- Extract the core search query from the user prompt (strip operational noise)
- Look for explicit document identifiers (UPPER_CASE_SNAKE_CASE patterns)
- Look for quoted document names as secondary signals
- Use the full prompt as fallback for standalone RAG queries
- Request enough chunks to provide comprehensive coverage (top 5-10)

## Chunk Quality Rules
- Prefer chunks with high relevance scores
- Include source_name and source_uri (GCS URI) with every chunk
- Filter out chunks that are too short (< 20 characters) — likely noise
- Deduplicate chunks from the same source document
- When multiple chunks come from the same document, preserve order

## Output Format
Return a list of curated context chunks, each containing:
- text: The relevant content snippet
- source_name: Human-readable document name
- source_uri: Full GCS URI for citation tracking

## Error Handling
- Redis cache miss: proceed with live search (no error)
- Vertex AI unavailable: return empty chunks, log warning
- Empty results: transparently tell user no documents matched
- Never fabricate search results or source citations
