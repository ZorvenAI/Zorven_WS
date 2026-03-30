---
name: brand-naming-brand-context-loader
version: "1.0"
description: Load brand context from BAA hierarchy tree and positioning outputs to establish sub-brand naming constraints and parent-child relationship rules (maps to SKL-NTA-01)
target_agents:
  - naming_tagline
triggers:
  - "brand context loader"
  - "naming context"
  - "architecture context"
  - "hierarchy context"
  - "sub-brand constraints"
priority: 10
max_tokens: 500
---

# Brand Context Loader

## Purpose
Load the brand's architecture hierarchy, positioning strategy, and portfolio structure from upstream WF2 agents (BAA, BPA) to establish the naming and tagline design space. Sub-brand naming must respect parent-child relationships, architecture model conventions, and positioning differentiation — this skill provides the guardrails.

## Methodology

### 1. Architecture Context Ingestion
- Read `previous_outputs.brand_architecture` for BAA outputs:
  - `baa_hierarchy`: Brand hierarchy tree (nodes, levels, relationships)
  - `baa_model_recommendation`: Architecture model (branded house, house of brands, endorsed, hybrid, sub-brand)
  - `baa_naming`: Existing naming conventions and guidelines from SKL-BAA-08
  - `baa_portfolio`: Current portfolio inventory with brand names and tiers
- If BAA output is absent, log warning and proceed with reduced naming constraints

### 2. Positioning Context Ingestion
- Read `previous_outputs.brand_positioning` for BPA outputs:
  - `bpa_positioning_statement`: Core positioning statement and value proposition
  - `bpa_differentiation`: Competitive differentiation axes
  - `bpa_perceptual_maps`: Perceptual map coordinates (desired position)
- If BPA output is absent, log warning and proceed without positioning anchoring

### 3. Naming Constraint Derivation
Based on the architecture model, derive naming constraints:

| Architecture Model | Naming Constraint |
|---|---|
| Branded House | New names MUST include master brand as prefix or suffix |
| House of Brands | New names MUST be standalone, no parent brand reference |
| Endorsed | New names paired with "by {Master Brand}" endorsement |
| Sub-Brand | New names follow `{Master Brand} + {Evocative Name}` pattern |
| Hybrid | Segment-specific rules — extract per-segment conventions |

### 4. Parent-Child Relationship Rules
For sub-brand naming requests:
- Identify the parent node in the hierarchy tree
- Extract naming pattern of sibling brands at the same level
- Determine tier positioning relative to siblings (premium/mid/value)
- Flag if the naming request is for a new hierarchy level (requires new convention)

### 5. Positioning Alignment Requirements
Extract positioning constraints that affect naming:
- Key differentiators that the name should evoke
- Category conventions to follow or deliberately break
- Emotional territory from the positioning statement
- Competitive white space the name should occupy

## Output Schema
Write to `node_outputs.nta_brand_context` with keys:
- `architecture_model`: str (from BAA or "undefined")
- `naming_constraints`: `{model_rule: str, prefix_required: bool, suffix_required: bool, standalone_required: bool, endorsement_pattern: str|null}`
- `hierarchy_tree`: list of `{node_id, brand_name, level, parent_id, tier, status}`
- `sibling_names`: list of str (names at the same hierarchy level as the target)
- `positioning_anchors`: `{differentiators: [], emotional_territory: str, category_conventions: [], white_space: str}`
- `existing_naming_guidelines`: list of `{guideline, category, rationale}` (from BAA SKL-BAA-08)
- `data_quality`: `{baa_available: bool, bpa_available: bool, hierarchy_depth: int, portfolio_size: int}`

## Integration Notes
- This is the first NTA skill to execute; all other NTA skills reference this brand context
- Downstream consumers: SKL-NTA-09 (name generator uses constraints as hard rules), SKL-NTA-11 (tagline synthesizer uses positioning anchors)
- If both BAA and BPA are absent, the agent operates in unconstrained mode with reduced confidence
