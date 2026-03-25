---
name: brand-personality-emotional-mapper
version: "1.0"
description: Validate per-persona emotional intensity scores (0-100) mapping brand personality traits to audience-specific emotional responses for targeted communication (maps to SKL-BPV-08)
target_agents:
  - brand_personality
triggers:
  - "emotional mapper"
  - "emotional intensity"
  - "emotional attributes"
  - "persona emotions"
  - "emotional map"
priority: 9
max_tokens: 500
---

# Emotional Attribute Mapper

## Purpose
Create a persona-specific emotional intensity map that translates the brand personality into targeted emotional responses. Different audience segments respond to different emotional registers — this skill ensures the personality is expressed with appropriate emotional calibration per persona.

## Methodology

### 1. Input Collection
- Read SKL-BPV-05 `bpv_aaker_profile` for personality dimensions and sub-traits (required)
- Read SKL-BPV-01 `bpv_audience_psychology` for persona-specific emotional receptivity profiles (required)
- Read SKL-BPV-06 `bpv_archetype` for archetype emotional register (enriching)
- If audience psychology is absent, generate a single default persona with uniform emotional intensity

### 2. Emotional Attribute Set
Define the brand's emotional attribute palette based on the Aaker profile:

| Aaker Dimension | Emotional Attributes |
|---|---|
| Sincerity | Trust, Warmth, Comfort, Nostalgia, Gratitude |
| Excitement | Thrill, Curiosity, Surprise, Energy, Anticipation |
| Competence | Confidence, Assurance, Respect, Pride, Clarity |
| Sophistication | Admiration, Aspiration, Elegance, Exclusivity, Delight |
| Ruggedness | Empowerment, Determination, Freedom, Grit, Adventure |

- Select 6-10 emotional attributes based on primary and secondary dimensions
- Include at least 2 attributes from the primary dimension and 2 from the secondary

### 3. Per-Persona Intensity Scoring
For each persona from SKL-BPV-01, score each emotional attribute on a 0-100 intensity scale:
- **0-20**: Minimal expression — attribute is present but subdued
- **21-40**: Moderate — noticeable undertone in communication
- **41-60**: Balanced — clearly expressed but not dominant
- **61-80**: Strong — prominent emotional driver in interactions
- **81-100**: Dominant — the defining emotional quality for this persona

Scoring factors:
- Persona emotional receptivity profile (from SKL-BPV-01)
- Persona communication preference (formal reduces intensity, casual increases)
- Persona life stage and context (professional vs. personal interactions)
- Archetype relationship dynamic (mentor archetypes use authority emotions, companion archetypes use warmth emotions)

### 4. Intensity Validation Rules
- No persona should have all attributes above 80 (emotional overload)
- No persona should have all attributes below 30 (emotional flatness)
- The primary Aaker dimension's attributes should average highest across all personas
- Standard deviation of intensities per persona should be > 15 (differentiation)
- Flag personas where emotional profile contradicts their stated preferences

### 5. Cross-Persona Consistency Check
- The brand's emotional core (top 3 attributes) should be consistent across personas (within +/-20 intensity)
- Persona-specific variations should be in secondary/tertiary attributes
- Compute `emotional_consistency` score (0-100): how consistent the emotional core is across personas

## Output Schema
Write to `node_outputs.bpv_emotional_map` with keys:
- `emotional_attributes`: list of `{attribute, aaker_dimension, brand_baseline_intensity: int}`
- `persona_intensity_map`: list of `{persona_name, intensities: {attribute: int, ...}, dominant_emotion, suppressed_emotions: []}`
- `emotional_core`: list of `{attribute, avg_intensity: int, consistency_across_personas: int}`
- `emotional_consistency`: int (0-100)
- `validation`: `{no_overload: bool, no_flatness: bool, primary_dominant: bool, sufficient_differentiation: bool}`
- `data_quality`: `{personas_mapped: int, attributes_selected: int, archetype_available: bool}`

## Integration Notes
- Downstream consumers: SKL-BPV-09 (voice matrix uses emotional intensities to calibrate tone per channel), SKL-BPV-10 (character brief references emotional map for behavioral guidelines)
- `emotional_consistency` < 40 triggers an advisory in SKL-BPV-12
- The emotional map is a bridge between abstract personality traits and concrete communication decisions
