---
name: audience-persona-methodology
version: "1.0"
description: Guide the Audience Persona Agent in constructing data-grounded buyer personas
target_agents:
  - audience_persona
triggers:
  - "persona"
  - "audience"
  - "buyer"
  - "demographic"
  - "psychographic"
  - "target market"
  - "customer segment"
priority: 10
max_tokens: 500
---
# Audience Persona Research Methodology

## Purpose

Guide the Audience Persona Agent in constructing data-grounded buyer personas using a multi-source research methodology.

## Methodology Framework

### Research Phase (Parallel)

1. **Audience Landscape Research**: Broad web search for target market demographics, psychographics, and behavioral patterns
2. **Forum & Community Mining**: Extract authentic customer voices from Reddit, Quora, industry forums, and online communities
3. **Social Listening Analysis**: Analyze social media behavior, content preferences, engagement patterns, and influencer dynamics
4. **Buyer Role Extraction**: Identify decision-makers, influencers, gatekeepers, and end-users in the buying process
5. **Review & Needs Mining**: Extract unmet needs, frustrations, and desires from product reviews and comparison sites
6. **RAG Context Retrieval**: Pull relevant context from the tenant's knowledge base

### Analysis Phase (Sequential)

7. **Demographic Profile Building**: Synthesize demographic attributes from research data and CRM records
8. **Psychographic & Behavioral Profiling**: Map values, interests, media habits, and decision-making styles
9. **Persona Synthesis & Differentiation**: Merge research into distinct, non-overlapping personas with clear differentiation
10. **Buying Journey Mapping**: Map each persona through awareness → consideration → evaluation → decision → onboarding → advocacy

## Key Principles

- **Data-grounded, never fictional**: Every persona attribute must be supported by research evidence or CRM data
- **Segment labels, not names**: Use descriptive segment labels (e.g., "Enterprise Decision Maker") — NEVER fictional human names
- **CRM-first when available**: When Odoo CRM has 10+ customers, ground persona segments in real customer data
- **Differentiation over quantity**: Fewer well-differentiated personas are better than many overlapping ones
- **Citation required**: Every claim must cite at least one source
- **Confidence scoring**: Flag low-confidence attributes for verification
