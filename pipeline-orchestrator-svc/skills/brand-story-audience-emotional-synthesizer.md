---
name: brand-story-audience-emotional-synthesizer
version: "1.0"
description: Synthesize APA emotional drivers and VoCA language patterns into an emotional arc for brand narrative generation (maps to SKL-BSA-02)
target_agents:
  - brand_story
triggers:
  - "emotional arc"
  - "audience emotions"
  - "emotional synthesis"
  - "narrative emotions"
priority: 10
max_tokens: 500
---

# Audience Emotional Synthesizer

## Purpose
Transform audience persona emotional drivers (from APA) and voice-of-customer language patterns (from VoCA) into an emotional arc structure that guides origin story crafting and narrative tone.

## Methodology

### 1. Extract Emotional Drivers
From WF1 context (APA personas):
- Primary emotional needs per persona segment
- Pain points and aspirations
- Trust triggers and skepticism barriers

### 2. Extract Language Patterns
From WF1 context (VoCA analysis):
- Sentiment distribution (positive/negative/neutral language)
- Key phrases and vocabulary customers use
- Emotional intensity indicators

### 3. Build Emotional Arc
Construct a 3-phase narrative emotional arc:
- **Tension**: Pain points, unmet needs, market frustration (draws from VoCA negative sentiment + APA pain points)
- **Transformation**: Brand promise, differentiation moment, archetype activation (draws from BPV archetype + BPA positioning)
- **Resolution**: Aspirational outcome, emotional payoff, loyalty trigger (draws from APA aspirations + brand values)

## Output Schema
Write to `node_outputs.bsa_emotional_arc` with keys:
- `arc`: dict with `tension`, `transformation`, `resolution` phases
- `primary_emotions`: list of target emotions ranked by resonance
- `language_register`: dict (formality_level, vocabulary_preferences, tone_markers)
- `persona_hooks`: dict mapping persona segments to specific emotional entry points

## Integration Notes
- Feeds into SKL-BSA-06 (Origin Story Crafter) for emotional arc integration
- Feeds into SKL-BSA-08 (Elevator Pitch Generator) for emotional hooks
- If VoCA data is absent, falls back to APA-only emotional synthesis
