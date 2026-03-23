---
name: brand-positioning-identity-context
version: "1.0"
description: Load brand identity anchor from Company model — mission, vision, values, personality (maps to SKL-BPA-04)
target_agents:
  - brand_positioning
triggers:
  - "brand identity"
  - "company identity"
  - "brand anchor"
  - "mission vision"
  - "brand values"
priority: 10
max_tokens: 350
---

# Brand Identity Context Loader

## Purpose
Extract the brand's foundational identity from the Company model and any prior Discovery Agent outputs. This anchor constrains all downstream positioning to remain authentic and consistent with the brand's established identity.

## Methodology

### 1. Company Model Extraction
- Read `input_context.company` for core brand identity fields:
  - `name`: Legal/trading brand name
  - `industry`: Primary industry vertical
  - `description`: Brand description or elevator pitch
  - `website`: Official domain (used for tone inference)
  - `target_market`: Intended audience description
- Read `input_context.company_id` for tenant-specific lookups

### 2. Discovery Agent Enrichment
- Read `previous_outputs.discovery` for web-researched brand intelligence (if available):
  - Brand history and founding story
  - Public brand positioning statements
  - Media tone and voice analysis
  - Key brand milestones
- Merge with Company model data, preferring Company model for factual fields and Discovery for narrative context

### 3. Brand Identity Anchor Construction
Assemble a structured identity anchor with the following components:

| Component | Source | Fallback |
|-----------|--------|----------|
| **Mission** | Company description or Discovery findings | Infer from industry + target market |
| **Vision** | Discovery brand narrative | Mark as "not explicitly stated" |
| **Values** | Discovery cultural signals | Derive 3-5 from industry norms |
| **Personality** | Discovery tone analysis | Default to professional, authoritative |
| **Category** | Company industry field | Infer from description |
| **Current Positioning** | Discovery public statements | Mark as "no prior positioning found" |

### 4. Constraint Boundaries
- Define positioning guardrails: any generated positioning MUST align with the identity anchor
- Flag conflicts between Company model data and Discovery findings for human review
- Set `identity_confidence` score (0-1) based on data completeness

## Output Schema
Write to `node_outputs.bpa_identity_context` with keys:
- `brand_name`: str
- `industry`: str
- `mission`: str
- `vision`: str or null
- `values`: list of str
- `personality_traits`: list of str
- `category`: str
- `current_positioning`: str or null
- `identity_confidence`: float (0-1)
- `guardrails`: list of constraint strings
- `data_sources`: list of `{source: "company_model"|"discovery", fields_contributed: []}`

## Integration Notes
- This is typically the first BPA skill to execute; all other BPA skills reference the identity anchor
- If `identity_confidence` < 0.3, trigger SKL-BPA-12 (human escalation) for insufficient brand data
