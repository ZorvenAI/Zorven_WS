---
name: brand-personality-audience-psychology
version: "1.0"
description: Extract psychographic profiles from APA persona data and VoCA sentiment insights to inform personality trait weighting and emotional resonance targets (maps to SKL-BPV-01)
target_agents:
  - brand_personality
triggers:
  - "audience psychology"
  - "psychographic profile"
  - "persona insights"
  - "audience emotions"
  - "personality audience"
priority: 10
max_tokens: 500
---

# Audience Psychology Analyzer

## Purpose
Consume Audience Persona Agent (APA) and Voice of Customer Agent (VoCA) outputs to build a psychographic foundation for personality design. Understanding audience values, motivations, and emotional drivers ensures the brand personality resonates authentically with target segments.

## Methodology

### 1. APA Output Ingestion
- Read `previous_outputs.audience_persona` for persona profiles
- Extract per-persona: demographics, psychographics, motivations, pain points, media habits, values
- If APA output is absent, log warning and proceed with reduced psychographic depth

### 2. VoCA Sentiment Extraction
- Read `previous_outputs.voice_of_customer` for sentiment analysis and NPS data
- Extract: dominant emotions, satisfaction drivers, frustration triggers, brand associations, language patterns
- If VoCA output is absent, log warning and use APA data only

### 3. Psychographic Synthesis
For each persona, compute:
- **Value Alignment Score** (0-100): How strongly the persona's stated values match potential personality traits
- **Emotional Receptivity Profile**: Which emotional registers (trust, excitement, warmth, authority, creativity) the persona responds to
- **Communication Style Preference**: Formal vs. casual, technical vs. accessible, aspirational vs. pragmatic
- **Personality Trait Affinity**: Initial weighting of Aaker 5D traits based on audience expectations

### 4. Cross-Persona Consolidation
- Identify shared psychographic themes across all personas (consensus traits)
- Flag persona-specific divergences that may require persona-specific voice variations
- Compute a `psychographic_coherence` score (0-100): higher values mean personas share similar personality expectations
- Weight contributions by persona priority (primary personas contribute more)

### 5. Emotional Resonance Targets
Derive target emotional states the brand personality should evoke:
- **Primary Emotion**: The dominant emotional response desired (e.g., trust, inspiration)
- **Secondary Emotion**: Supporting emotional undertone
- **Avoidance Emotions**: Emotions the personality must not trigger (e.g., anxiety, confusion)

## Output Schema
Write to `node_outputs.bpv_audience_psychology` with keys:
- `persona_profiles`: list of `{persona_name, values, motivations, emotional_receptivity, communication_preference, trait_affinity}`
- `consensus_traits`: list of `{trait, strength: float, supporting_personas: int}`
- `divergences`: list of `{trait, persona_name, direction, severity}`
- `psychographic_coherence`: int (0-100)
- `emotional_targets`: `{primary_emotion, secondary_emotion, avoidance_emotions: []}`
- `data_quality`: `{apa_available: bool, voca_available: bool, personas_analyzed: int, sentiment_depth: str}`

## Integration Notes
- Downstream consumers: SKL-BPV-05 (Aaker profiler uses trait affinity as input weights), SKL-BPV-08 (emotional mapper uses emotional targets)
- If both APA and VoCA are absent, set all trait affinities to neutral (0.5) and `psychographic_coherence` to 0
- `psychographic_coherence` < 30 triggers an advisory note in SKL-BPV-12 (human escalation)
