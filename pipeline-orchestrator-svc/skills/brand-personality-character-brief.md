---
name: brand-personality-character-brief
version: "1.0"
description: Synthesize all BPV skill outputs into a unified character brief with personality summary, positioning alignment check, and implementation guidelines (maps to SKL-BPV-10)
target_agents:
  - brand_personality
triggers:
  - "character brief"
  - "personality synthesis"
  - "personality summary"
  - "brand character"
  - "personality document"
priority: 8
max_tokens: 700
---

# Character Brief Synthesizer

## Purpose
Produce the capstone character brief by synthesizing outputs from all preceding skills (SKL-BPV-01 through SKL-BPV-09). This document is the primary deliverable of the Brand Personality Agent — a comprehensive, actionable personality profile that downstream agents and human teams use to maintain brand consistency.

## Methodology

### 1. Input Aggregation
Collect and validate all upstream skill outputs:

| Source | Key | Required? |
|---|---|---|
| SKL-BPV-01 | `bpv_audience_psychology` | Enriching |
| SKL-BPV-02 | `bpv_brand_perception` | Enriching |
| SKL-BPV-03 | `bpv_identity_seed` | Required |
| SKL-BPV-04 | `bpv_rag_context` | Enriching |
| SKL-BPV-05 | `bpv_aaker_profile` | Required |
| SKL-BPV-06 | `bpv_archetype` | Required |
| SKL-BPV-07 | `bpv_values_hierarchy` | Required |
| SKL-BPV-08 | `bpv_emotional_map` | Required |
| SKL-BPV-09 | `bpv_voice_matrix` | Required |

Log completeness metrics: `{required_present, required_total, enriching_present, enriching_total}`.

### 2. Personality Summary (200-300 words)
Synthesize a narrative personality summary covering:
- Brand personality in human terms ("If this brand were a person...")
- Primary and secondary Aaker dimensions with plain-language descriptions
- Selected archetype and its meaning for the brand
- Core values and what they mean in practice
- Voice character in one sentence

### 3. Positioning Alignment Check
Cross-reference personality with positioning strategy:
- Read `previous_outputs.brand_positioning` for positioning statement and differentiation pillars
- Verify personality traits reinforce (not contradict) the positioning
- Check archetype aligns with positioning's competitive stance
- Compute `positioning_alignment` score (0-100)
- Flag any trait-positioning conflicts

### 4. Architecture Alignment Check
If BAA output is available in `previous_outputs.brand_architecture`:
- Verify personality is appropriate for the recommended architecture model
- For Branded House: personality must be scalable across all sub-brands
- For House of Brands: personality applies to the parent level, sub-brands may diverge
- Compute `architecture_alignment` score (0-100)

### 5. Implementation Guidelines
Generate practical guidelines for applying the personality:
- **Content Creation**: How to write in the brand's voice (reference voice matrix)
- **Visual Identity**: Personality-driven visual direction (colors, imagery, typography mood)
- **Customer Interactions**: How brand personality manifests in service touchpoints
- **Social Media**: Platform-specific personality expression
- **Crisis Communication**: How the personality adapts under pressure (archetype shadow management)

### 6. Confidence Scoring
Compute overall personality confidence (0.0-1.0):
- `profile_confidence` (0.3 weight): From SKL-BPV-05 Aaker profile confidence
- `data_completeness` (0.2 weight): % of required + enriching inputs present
- `values_coherence` (0.2 weight): hierarchy_coherence from SKL-BPV-07 / 100
- `voice_coherence` (0.15 weight): voice_coherence from SKL-BPV-09 / 100
- `positioning_alignment` (0.15 weight): positioning_alignment / 100

### 7. Citations
Compile all data sources referenced:
- WF1 agents used (APA, VoCA, TCIA, CIA, MRA)
- BPA positioning strategy reference
- BAA architecture strategy reference
- Company model data
- RAG documents retrieved

## Output Schema
Write to `node_outputs.bpv_character_brief` with keys:
- `personality_summary`: str (200-300 words)
- `aaker_profile`: `{dimensions, primary, secondary, dormant, sub_traits}`
- `archetype`: `{name, motto, relationship_dynamic, story_arc}`
- `values_hierarchy`: `{core: [], supporting: [], aspirational: []}`
- `emotional_map`: `{attributes: [], persona_map: []}`
- `voice_matrix`: `{dimensions, channel_matrix, do_list, dont_list}`
- `positioning_alignment`: int (0-100)
- `architecture_alignment`: int or null (0-100, null if BAA unavailable)
- `implementation_guidelines`: `{content, visual, customer_interactions, social_media, crisis}`
- `confidence_score`: float (0.0-1.0)
- `confidence_breakdown`: `{profile_confidence, data_completeness, values_coherence, voice_coherence, positioning_alignment}`
- `data_completeness`: `{required_present, required_total, enriching_present, enriching_total}`
- `citations`: list of `{source_type, source_id, description}`
- `findings`: list of str (key findings for result_data)
- `recommendations`: list of str (key recommendations for result_data)

## Integration Notes
- This is the terminal analytical skill; its output becomes the primary `result_data` returned to Django
- SKL-BPV-11 (persister) archives this full character brief
- SKL-BPV-12 (escalation) uses `confidence_score` to determine if human review is needed
- The Django `BrandPersonalityExtractor` reads from this output to extract analytics metrics
- `confidence_score` < 0.7 triggers escalation
