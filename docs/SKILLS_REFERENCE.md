# Dynamic Skill Loading — Skills Reference

> **Version**: 1.0 | **Last Updated**: March 2026

## Overview

The AI Brand Automator uses a dynamic skill loading system that injects contextual instructions into agent LLM prompts at runtime. Skills are Markdown files with YAML frontmatter that the pipeline orchestrator loads at startup, matches against user prompts via trigger phrases, and injects into the target agent's config payload.

**How it works:**
```
User prompt → Orchestrator → SkillRouter matches triggers → skill_context injected into agent config → Agent appends to LLM prompt
```

**Adding a new skill:** Create a `.md` file in `pipeline-orchestrator-svc/skills/` with YAML frontmatter — no code changes needed (unless targeting an agent that doesn't yet have `skill_context` wired).

---

## Skills Inventory

### Content Agent (`blog_author`)

| Skill | Priority | Purpose | Example Prompt |
|-------|----------|---------|----------------|
| **persona-enforcer** | 15 | Enforces tenant-specific brand tone (Corporate, Playful, Technical, Inspirational) from brand_profile. Constrains the LLM to the tenant's voice throughout all generated content. | *"Write a blog post about our Q4 results"* |
| **geo-citation-manager** | 12 | Ensures citations prioritize tenant knowledge base (RAG) over public web sources. Prevents external data from overwriting proprietary insights. | *"Write a research-backed article citing our uploaded reports"* |
| **seo-content-guidelines** | 10 | Advanced SEO optimization: keyword placement, meta descriptions, E-E-A-T signals, content structure for SERP ranking. | *"Write an SEO-optimized blog about brand equity"* |
| **brand-voice-consistency** | 8 | Maintains consistent brand voice and messaging framework across content. Adapts tone to persona type. (Also targets social_promoter.) | *"Create brand-aligned content about our new product"* |
| **citation-quality** | 5 | Source selection, inline citation format, data integrity. Ensures claims are backed by provided sources only. | *"Write a data-driven article with research citations"* |

### Social Agent (`social_promoter`)

| Skill | Priority | Purpose | Example Prompt |
|-------|----------|---------|----------------|
| **social-tenant-orchestrator** | 12 | Role-based publishing flow: ADMIN/OWNER → direct publish via MCP, EDITOR → draft + pause for approval, VIEWER → reject. Handles MCP integration and error recovery. | *"Publish this to LinkedIn and Twitter"* |
| **social-platform-best-practices** | 10 | Platform-specific engagement tactics: LinkedIn hooks, Twitter brevity, Facebook questions, Instagram hashtag strategy. Cross-platform adaptation rules. | *"Promote our latest blog on social media"* |
| **brand-voice-consistency** | 8 | (Shared with blog_author) Maintains consistent brand voice across social posts. | *"Post a brand update on all platforms"* |

### Default Agent / RAG (`default_agent`)

| Skill | Priority | Purpose | Example Prompt |
|-------|----------|---------|----------------|
| **knowledge-retrieval-tool** | 10 | Vertex AI Search integration: tenant-to-data-store mapping, search query extraction, chunk quality filtering, source attribution. | *"Search my documents for revenue projections"* |
| **context-synthesizer** | 8 | Blends RAG document data with chat history. Answer relevancy check: grounded (cite docs) vs ungrounded ("I couldn't find that in your documents, but..."). | *"What does our brand guidelines document say about logo usage?"* |

### Intelligence Agent (`valuation_logic`, `gap_analyzer`)

| Skill | Priority | Purpose | Example Prompt |
|-------|----------|---------|----------------|
| **competitive-analysis-methodology** | 10 | ISO 10668 framework guidance, competitive gap quantification, BSI pillar evaluation, actionable recommendation structure. | *"Analyze our competitive position against market leaders"* |

### Manager Node (`manager`)

| Skill | Priority | Purpose | Example Prompt |
|-------|----------|---------|----------------|
| **manifest-ui-mapper** | 10 | Generates `ui_schema` in result_data telling the frontend which charts to render: radar_chart for BSI pillars, score_gauge, valuation_card, platform_cards, etc. | *"Run a full brand analysis report"* |

### Discovery Agent (`web_research`)

| Skill | Priority | Purpose | Example Prompt |
|-------|----------|---------|----------------|
| **discovery-event-tracer** | 10 | Emits real-time Kafka trace events as the agent browses URLs. Users see "Browsing (2/5): {title}" in ThoughtTrace UI. CloudEvents-compatible schema. | *"Research Tesla's market position"* |

### RAG Uploader (`rag_uploader`)

| Skill | Priority | Purpose | Example Prompt |
|-------|----------|---------|----------------|
| **smart-titler** | 10 | Generates professional descriptive filenames for generic uploads (e.g., "upload.pdf" → "Q4_Revenue_Analysis_Report.pdf"). GCS-compatible slugification. | *"Archive the uploaded documents to the knowledge base"* |
| **ingestion-bridge** | 8 | Data ingestion pipeline payload formatting: tenant routing via X-Tenant-ID, IngestionEvent schema, deduplication, error handling. | *"Store this file in our RAG index"* |

### Chat Titling Worker (`chat_titler`)

| Skill | Priority | Purpose | Example Prompt |
|-------|----------|---------|----------------|
| **session-titler** | 10 | Summarizes complex user intent into 3-5 word navigation-friendly session titles. Intent extraction patterns for research, content, task, question, and document requests. | *(Triggered automatically after first chat response)* |

---

## Skill File Format

```yaml
---
name: skill-name              # Unique identifier
version: "1.0"                # Semantic version
description: Brief purpose     # Shown in formatted context header
target_agents:                 # Which agents receive this skill
  - blog_author
  - social_promoter
triggers:                      # Substring matches against user prompt (OR logic)
  - "keyword"
  - "another trigger"
priority: 10                   # Higher = preferred when multiple match (descending)
max_tokens: 400                # Token budget estimate for this skill
---
# Skill Title

## Instructions
- Detailed instructions for the LLM...
```

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| Max skills per node | 3 | Maximum skills injected into a single agent prompt |
| Max total tokens | 1500 | Token budget cap across all matched skills per node |
| Skills directory | `pipeline-orchestrator-svc/skills/` | Central skill registry |
| Hot reload endpoint | `POST /v1/admin/reload-skills` | Reload skills without restart (requires X-Service-Token) |

## Agent Skill Support

| Agent | Node ID | `skill_context` Wired | Skills Count |
|-------|---------|----------------------|--------------|
| Content (blog) | `blog_author` | Yes | 5 |
| Social | `social_promoter` | Yes | 3 |
| Default (RAG) | `default_agent` | Yes | 2 |
| Intelligence | `valuation_logic`, `gap_analyzer` | Yes | 1 |
| Manager | `manager` | Yes | 1 |
| Discovery | `web_research` | Yes | 1 |
| RAG Uploader | `rag_uploader` | Yes | 2 |
| Chat Titling | `chat_titler` | Yes | 1 |
| **Total** | | **All agents** | **15** |
