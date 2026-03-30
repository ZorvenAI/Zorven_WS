---
name: brand-naming-name-generator
version: "1.0"
description: Build structured Claude prompt for brand name generation using upstream context, constraints, and creative direction to produce diverse name candidates (maps to SKL-NTA-09)
target_agents:
  - naming_tagline
triggers:
  - "name generator"
  - "generate names"
  - "name candidates"
  - "brand name creation"
  - "naming generation"
priority: 10
max_tokens: 600
---

# Brand Name Generator

## Purpose
Construct a structured Claude prompt that synthesizes all upstream context (brand architecture, audience psychology, competitive landscape, personality, and RAG history) into a creative brief for generating 10-15 diverse brand name candidates. The prompt must balance creative freedom with strategic constraints.

## Methodology

### 1. Input Assembly
Collect and validate all upstream skill outputs:
- SKL-NTA-01 `nta_brand_context`: Architecture constraints and positioning anchors (required)
- SKL-NTA-02 `nta_audience_psychology`: Audience preferences and emotional targets (enriching)
- SKL-NTA-03 `nta_competitive_naming`: White space and category conventions (enriching)
- SKL-NTA-04 `nta_identity_seed`: Personality constraints and voice guidelines (enriching)
- SKL-NTA-05 `nta_rag_context`: Prior approved/rejected names (enriching)

If the required brand context is absent, use Company model data with reduced constraint specificity.

### 2. Prompt Construction
Build a multi-section Claude prompt:

**Section 1 — Brand Brief**:
- Brand name (parent), industry, description, target market
- Architecture model and naming convention rules (from SKL-NTA-01)
- Positioning statement and key differentiators (from SKL-NTA-01)

**Section 2 — Creative Direction**:
- Personality-aligned naming style (from SKL-NTA-04)
- Archetype metaphor domains (from SKL-NTA-04)
- Audience tone and vocabulary preferences (from SKL-NTA-02)
- Emotional targets the name should evoke (from SKL-NTA-02)

**Section 3 — Competitive Landscape**:
- Competitor names to differentiate from (from SKL-NTA-03)
- White space opportunities to explore (from SKL-NTA-03)
- Category conventions to follow or break (from SKL-NTA-03)

**Section 4 — Constraints**:
- Hard constraints: architecture model rules, core value anti-associations, prior rejected names
- Soft constraints: audience preferences, voice guidelines, competitive differentiation
- Practical constraints: prefer names with domain/handle potential (short, spellable, unique)

**Section 5 — Output Requirements**:
- Generate 10-15 diverse candidates spanning at least 3 naming patterns
- For each candidate provide: name, naming pattern (descriptive/evocative/invented/compound/borrowed), rationale, intended emotional associations, pronunciation guide (if non-obvious)
- Include at least 2 "safe" candidates (category-conventional) and 2 "bold" candidates (convention-breaking)

### 3. Diversity Enforcement
Ensure the prompt requests candidates across multiple naming patterns:
- At least 2 evocative names
- At least 2 invented/coined names
- At least 2 compound names
- At least 1 borrowed/foreign-origin name
- At least 1 descriptive name
- Remaining slots for the pattern best aligned with brand personality

### 4. Candidate Parsing
Parse Claude's response into structured candidate objects:
- Validate each candidate has: name, pattern_type, rationale, emotional_associations
- Flag duplicates or near-duplicates
- Sort candidates by pattern diversity

## Output Schema
Write to `node_outputs.nta_name_candidates` with keys:
- `candidates`: list of `{name, pattern_type, rationale, emotional_associations: [], pronunciation_guide: str|null, category: "safe"|"bold"|"balanced"}`
- `total_candidates`: int
- `pattern_coverage`: `{descriptive: int, evocative: int, invented: int, compound: int, borrowed: int, other: int}`
- `prompt_context_used`: `{brand_context: bool, audience: bool, competitive: bool, identity: bool, rag: bool}`
- `generation_metadata`: `{model: str, temperature: float, prompt_tokens: int}`

## Integration Notes
- This skill produces the core creative output of the NTA agent
- Downstream consumers: SKL-NTA-06 (domain checker), SKL-NTA-07 (social handle checker), SKL-NTA-08 (trademark searcher), SKL-NTA-10 (name scorer)
- Availability/trademark checks (SKL-NTA-06, 07, 08) run after this skill and before scoring (SKL-NTA-10)
- The prompt uses Claude Sonnet 4 via the NTA agent's configured LLM client
