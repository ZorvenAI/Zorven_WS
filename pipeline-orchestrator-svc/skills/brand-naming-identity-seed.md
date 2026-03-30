---
name: brand-naming-identity-seed
version: "1.0"
description: Load brand identity and values from BPV personality profile to ensure naming alignment with established brand character, voice, and value hierarchy (maps to SKL-NTA-04)
target_agents:
  - naming_tagline
triggers:
  - "identity seed"
  - "personality seed"
  - "values alignment"
  - "naming identity"
  - "brand voice naming"
priority: 10
max_tokens: 500
---

# Identity & Values Seed Loader

## Purpose
Extract the brand's established personality, values, and voice characteristics from the Brand Personality & Values Agent (BPV) outputs. Names and taglines must be congruent with the brand's personality profile — a rugged brand cannot have a delicate name, and a sophisticated brand cannot have a casual tagline.

## Methodology

### 1. BPV Output Ingestion
- Read `previous_outputs.brand_personality` for personality profile:
  - `bpv_aaker_profile`: Aaker 5D dimension scores and primary/secondary dimensions
  - `bpv_archetype`: Selected brand archetype and rationale
  - `bpv_values_hierarchy`: Core, aspirational, and permission-to-play values
  - `bpv_voice_matrix`: Voice dimensions, channel adaptations, do/don't lists
  - `bpv_character_brief`: Synthesized character brief with confidence score
- If BPV output is absent, fall back to Company model `brand_voice` and `values` fields

### 2. Personality-to-Naming Constraints
Map the Aaker 5D profile to naming style constraints:

| Primary Dimension | Naming Style Guidance |
|---|---|
| Sincerity | Warm, familiar, real words; avoid pretentious or artificial names |
| Excitement | Bold, energetic, unexpected; neologisms and playful compounds welcome |
| Competence | Clear, authoritative, professional; descriptive or acronym patterns |
| Sophistication | Elegant, refined, premium; borrowed words, French/Italian influences |
| Ruggedness | Strong, simple, direct; short punchy names, Anglo-Saxon roots |

### 3. Archetype Alignment
Map the brand archetype to naming character:
- Extract the primary archetype (e.g., Hero, Creator, Explorer)
- Derive naming character traits: heroic names sound different from nurturing names
- Identify archetype-congruent metaphor domains (e.g., Explorer -> geography, journey, horizon)

### 4. Values Integration
From the values hierarchy, extract naming constraints:
- **Core Values**: Name must not contradict these (hard constraint)
- **Aspirational Values**: Name may evoke these as stretch goals
- **Permission-to-Play Values**: Baseline expectations, not differentiators
- Map each core value to naming associations and anti-associations

### 5. Voice Matrix Integration
Extract voice characteristics relevant to naming:
- Formality level (affects name register)
- Humor tolerance (affects playfulness of name candidates)
- Technical vs. accessible language preference
- Do/don't lists that apply to naming (e.g., "Don't use slang" constrains candidate generation)

## Output Schema
Write to `node_outputs.nta_identity_seed` with keys:
- `aaker_profile`: `{primary_dimension: str, secondary_dimension: str, scores: {sincerity, excitement, competence, sophistication, ruggedness}}`
- `naming_style_constraints`: `{style_guidance: str, permitted_patterns: [], prohibited_patterns: [], metaphor_domains: []}`
- `archetype`: `{name: str, naming_character: str, congruent_metaphors: []}`
- `values_constraints`: `{core_values: [{value, naming_associations: [], anti_associations: []}], aspirational_values: []}`
- `voice_constraints`: `{formality: str, humor_tolerance: str, language_register: str, do_list: [], dont_list: []}`
- `data_quality`: `{bpv_available: bool, confidence_score: float, fallback_used: bool}`

## Integration Notes
- Downstream consumers: SKL-NTA-09 (name generator uses style constraints and metaphor domains), SKL-NTA-10 (name scorer evaluates personality alignment), SKL-NTA-11 (tagline synthesizer uses voice constraints)
- If BPV output is absent, fall back to Company model with reduced confidence (0.3 cap)
- Personality alignment is a scoring factor, not a hard veto — creative exceptions with strong rationale are permitted
