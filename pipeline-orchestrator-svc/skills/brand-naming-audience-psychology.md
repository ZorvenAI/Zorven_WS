---
name: brand-naming-audience-psychology
version: "1.0"
description: Analyze audience psychographics from APA and VoCA outputs to determine name resonance factors, linguistic preferences, and emotional triggers for naming decisions (maps to SKL-NTA-02)
target_agents:
  - naming_tagline
triggers:
  - "audience psychology"
  - "naming psychology"
  - "audience resonance"
  - "psychographic naming"
  - "name preferences"
priority: 10
max_tokens: 500
---

# Audience Psychology Analyzer

## Purpose
Consume Audience Persona Agent (APA) and Voice of Customer Agent (VoCA) outputs to build a psychographic profile that informs name and tagline resonance. Names that align with audience values, linguistic habits, and emotional expectations achieve higher recall and preference.

## Methodology

### 1. APA Output Ingestion
- Read `previous_outputs.audience_persona` for persona profiles
- Extract per-persona: demographics (age, education, profession), psychographics (values, lifestyle), communication preferences, brand affinities, media consumption
- If APA output is absent, log warning and proceed with reduced audience depth

### 2. VoCA Sentiment Extraction
- Read `previous_outputs.voice_of_customer` for sentiment and language patterns
- Extract: dominant vocabulary, positive brand associations, language register (formal/casual), jargon tolerance, emotional triggers
- If VoCA output is absent, log warning and use APA data only

### 3. Linguistic Preference Profiling
For each persona, compute:
- **Vocabulary Level**: Simple (grade 6-8), moderate (grade 9-12), sophisticated (college+)
- **Name Length Preference**: Short (1-2 syllables), medium (3-4), long (5+)
- **Tone Preference**: Playful, professional, aspirational, earthy, technical
- **Cultural Sensitivity Flags**: Languages spoken, cultural taboos, religious considerations
- **Memorability Factors**: Alliteration preference, rhyme receptivity, neologism tolerance

### 4. Cross-Persona Consolidation
- Identify shared linguistic preferences across all personas
- Flag persona-specific divergences that may require variant naming approaches
- Compute a `naming_coherence` score (0-100): higher values mean personas share similar naming expectations
- Weight contributions by persona priority (primary personas contribute more)

### 5. Emotional Resonance Targets
Derive target emotional associations the brand name should evoke:
- **Primary Association**: The dominant feeling triggered by the name (e.g., trust, innovation, warmth)
- **Secondary Association**: Supporting emotional undertone
- **Avoidance Associations**: Emotions or connotations the name must not trigger

## Output Schema
Write to `node_outputs.nta_audience_psychology` with keys:
- `persona_profiles`: list of `{persona_name, vocabulary_level, name_length_pref, tone_pref, cultural_flags: [], memorability_factors: {}}`
- `consensus_preferences`: `{vocabulary_level: str, tone: str, name_length: str, neologism_tolerance: str}`
- `divergences`: list of `{preference, persona_name, direction, severity}`
- `naming_coherence`: int (0-100)
- `emotional_targets`: `{primary_association: str, secondary_association: str, avoidance_associations: []}`
- `data_quality`: `{apa_available: bool, voca_available: bool, personas_analyzed: int, sentiment_depth: str}`

## Integration Notes
- Downstream consumers: SKL-NTA-09 (name generator uses preferences as soft constraints), SKL-NTA-10 (name scorer uses resonance targets for scoring), SKL-NTA-11 (tagline synthesizer uses tone preferences)
- If both APA and VoCA are absent, set all preferences to neutral defaults and `naming_coherence` to 0
- `naming_coherence` < 30 triggers an advisory note in SKL-NTA-14 (human escalation)
