---
name: brand-personality-values-hierarchy
version: "1.0"
description: Construct and validate values hierarchy with 3 tiers — core values (3-5), supporting values (3-5), and aspirational values (1-3) — aligned to Aaker profile and brand identity (maps to SKL-BPV-07)
target_agents:
  - brand_personality
triggers:
  - "values hierarchy"
  - "brand values"
  - "core values"
  - "values tiers"
  - "values design"
priority: 9
max_tokens: 500
---

# Values Hierarchy Builder

## Purpose
Design a structured values hierarchy that translates the Aaker personality profile into actionable brand values. Values are organized into three tiers — core (non-negotiable), supporting (operational), and aspirational (future-facing) — creating a practical framework for brand decision-making.

## Methodology

### 1. Input Collection
- Read SKL-BPV-05 `bpv_aaker_profile` for dimension scores and primary/secondary dimensions (required)
- Read SKL-BPV-03 `bpv_identity_seed` for declared brand values (required)
- Read SKL-BPV-06 `bpv_archetype` for archetype narrative context (enriching)
- Read SKL-BPV-02 `bpv_brand_perception` for perception gap insights (enriching)

### 2. Tier Definitions

| Tier | Count | Purpose | Stability |
|---|---|---|---|
| **Core** | 3-5 | Non-negotiable identity anchors; define what the brand stands for | Permanent (should rarely change) |
| **Supporting** | 3-5 | Operational values that guide daily brand behavior and decisions | Stable (reviewed annually) |
| **Aspirational** | 1-3 | Future-state values the brand is growing toward | Evolving (updated with strategy) |

### 3. Core Values Generation
Derive core values from the intersection of:
- Primary Aaker dimension traits (highest weight)
- Declared brand values from Company model (founder intent)
- Archetype core desire (if available)
- Rules:
  - Each core value must map to at least one Aaker dimension
  - At least one core value must align with the primary dimension
  - Values must be distinct (no synonyms within the same tier)
  - Express as single words or two-word phrases (e.g., "Authentic Innovation")

### 4. Supporting Values Generation
Derive supporting values from:
- Secondary Aaker dimension traits
- Audience expectations (from SKL-BPV-01 consensus traits)
- Industry table-stakes values (category essentials)
- Rules:
  - Supporting values operationalize core values (e.g., core "Innovation" -> supporting "Continuous Learning")
  - Must not contradict any core value
  - At least one value should address a perception gap (from SKL-BPV-02)

### 5. Aspirational Values Generation
Derive aspirational values from:
- Perception gaps where the brand wants to grow
- Cultural opportunities (from SKL-BPV-02)
- Archetype growth arc (from SKL-BPV-06)
- Rules:
  - Must represent genuine growth areas, not current strengths
  - Should be achievable within 2-3 years
  - Must not contradict core values

### 6. Hierarchy Validation
- **Completeness**: 3-5 core, 3-5 supporting, 1-3 aspirational (hard constraint)
- **Consistency**: No contradictions between tiers
- **Distinctiveness**: No duplicate or synonymous values across tiers
- **Aaker Coverage**: All 5 dimensions represented across the full hierarchy
- **Actionability**: Each value can be translated into observable brand behaviors
- Compute `hierarchy_coherence` score (0-100)

## Output Schema
Write to `node_outputs.bpv_values_hierarchy` with keys:
- `core_values`: list of `{value, description, aaker_dimension, behavioral_indicator}`
- `supporting_values`: list of `{value, description, aaker_dimension, behavioral_indicator}`
- `aspirational_values`: list of `{value, description, aaker_dimension, target_timeline, growth_indicator}`
- `hierarchy_coherence`: int (0-100)
- `aaker_coverage`: `{sincerity: int, excitement: int, competence: int, sophistication: int, ruggedness: int}` (values mapped per dimension)
- `validation`: `{total_values: int, tier_compliance: bool, no_contradictions: bool, no_duplicates: bool, all_dimensions_covered: bool}`

## Integration Notes
- Downstream consumers: SKL-BPV-10 (character brief includes values hierarchy), SKL-BPV-09 (voice matrix references core values for tone guidance)
- `hierarchy_coherence` < 50 triggers an advisory in SKL-BPV-12
- Tier count violations (outside 3-5/3-5/1-3 ranges) trigger a warning in SKL-BPV-12
- Values hierarchy is persisted by SKL-BPV-11 for brand context sync to Django
