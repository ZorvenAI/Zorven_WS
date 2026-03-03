---
name: geo-citation-manager
version: "1.0"
description: Ensure citations prioritize tenant knowledge base over public web sources
target_agents:
  - blog_author
triggers:
  - "blog"
  - "write"
  - "article"
  - "content"
  - "cite"
  - "source"
  - "research"
  - "data"
  - "reference"
priority: 12
max_tokens: 400
---
# GEO CitationManager — Tenant Knowledge Base Citation Priority

## Purpose
Ensure all data-backed claims in generated content are cited from the
tenant's own uploaded documents (knowledge base) first, with public web
sources as secondary. Prevents "public noise" from overwriting proprietary
insights found in tenant files.

## Citation Priority Hierarchy
1. **Tenant Knowledge Base** (highest priority)
   - Documents uploaded by the tenant via the file uploader
   - RAG-indexed content from Vertex AI Search
   - Source identified by GCS URI or file name from tenant's data store
   - Always cite with the document's actual file name

2. **Discovery Research** (secondary)
   - Web research from the discovery-agent (Tavily API results)
   - Only use when tenant documents don't cover the topic
   - Always attribute with [Source Title](URL) format
   - Mark as external source when mixing with tenant data

3. **General Knowledge** (last resort)
   - LLM training data, no specific citation available
   - Be transparent: "Based on general industry knowledge..."
   - Never fabricate a source citation for general knowledge

## Filtering Rules
- When previous_outputs contains both `default_agent` (RAG) and `web_research` data:
  - Prefer `default_agent.raw_context` over `web_research.raw_context`
  - Use web research only to fill gaps not covered by tenant documents
  - If the same claim appears in both sources, cite the tenant document
- When the tenant's documents directly contradict public sources:
  - Prioritize the tenant's data (it's their proprietary context)
  - Do NOT mention the contradiction unless explicitly relevant

## Citation Format
- Inline Markdown links for web sources: [Source Title](URL)
- File name references for tenant documents: "According to [Brand_Guidelines.pdf]..."
- Place citations immediately after the supported claim
- Do NOT cluster all citations at the end of the article
- Each major claim should have its own attribution

## Quality Checks
- Never cite a source that wasn't provided in the research context
- Never invent URLs or fabricate document names
- If no sources support a claim, either remove the claim or explicitly
  mark it as the author's analysis/opinion
- Round-trip verify: every cited source name should appear in either
  the research context or the tenant's document list
