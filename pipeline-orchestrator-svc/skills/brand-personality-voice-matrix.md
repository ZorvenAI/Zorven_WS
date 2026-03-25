---
name: brand-personality-voice-matrix
version: "1.0"
description: Validate voice matrix structure defining tone, language, and communication style across channels and contexts with do/don't guidelines (maps to SKL-BPV-09)
target_agents:
  - brand_personality
triggers:
  - "voice matrix"
  - "tone of voice"
  - "communication style"
  - "brand voice"
  - "voice guidelines"
priority: 9
max_tokens: 600
---

# Voice Matrix Designer

## Purpose
Produce a comprehensive voice matrix that translates the brand personality, archetype, and emotional map into actionable communication guidelines. The voice matrix defines how the brand speaks across different channels, audiences, and contexts — it is the primary operational artifact for content creators and marketers.

## Methodology

### 1. Input Collection
- Read SKL-BPV-05 `bpv_aaker_profile` for personality dimensions (required)
- Read SKL-BPV-06 `bpv_archetype` for archetype narrative and relationship dynamic (required)
- Read SKL-BPV-08 `bpv_emotional_map` for per-persona emotional intensities (enriching)
- Read SKL-BPV-07 `bpv_values_hierarchy` for core values to embed in voice (enriching)
- Read `previous_outputs.brand_positioning` for positioning statement alignment (enriching)

### 2. Voice Dimension Framework
Define 4 voice dimensions, each expressed as a spectrum:

| Dimension | Spectrum | Driven By |
|---|---|---|
| **Formality** | Casual <-> Formal | Primary Aaker dimension + industry norms |
| **Energy** | Calm <-> Energetic | Excitement score + archetype energy level |
| **Warmth** | Detached <-> Warm | Sincerity score + archetype relationship dynamic |
| **Authority** | Peer <-> Expert | Competence score + brand market position |

For each dimension, assign a position on the spectrum (0-100 scale, 50 = neutral):
- 0-25: Strongly toward the left pole
- 26-50: Leaning left
- 51-75: Leaning right
- 76-100: Strongly toward the right pole

### 3. Channel Adaptation Matrix
Define voice variations across key channels:

| Channel | Formality Adj. | Energy Adj. | Warmth Adj. | Authority Adj. |
|---|---|---|---|---|
| Website (home) | +10 | +5 | +5 | +10 |
| Blog / long-form | -5 | 0 | +10 | +5 |
| Social media | -15 | +15 | +10 | -10 |
| Email marketing | -5 | +5 | +15 | 0 |
| Customer support | -10 | -5 | +20 | 0 |
| Sales / pitch | +10 | +10 | 0 | +15 |
| Internal comms | -20 | 0 | +10 | -5 |

Adjustments shift the base voice dimension scores. Clamp all adjusted scores to 0-100.

### 4. Language Guidelines
For each voice dimension position, generate concrete language guidance:
- **Vocabulary**: Preferred word types (e.g., "use active verbs", "avoid jargon")
- **Sentence Structure**: Length preferences, complexity level
- **Punctuation & Formatting**: Use of exclamation marks, emoji policy, capitalization style
- **Pronoun Usage**: First-person ("we"), second-person ("you"), third-person conventions

### 5. Do/Don't Lists
Generate behavioral do/don't guidelines:
- **Do**: 5-8 positive voice behaviors (e.g., "Do use storytelling to illustrate points")
- **Don't**: 5-8 negative voice behaviors (e.g., "Don't use condescending language")
- Each item references the source personality trait or value driving it
- Must cover all 4 voice dimensions

### 6. Voice Matrix Validation
- All 4 dimensions have assigned positions
- Channel adaptations produce valid scores (0-100 after adjustment)
- Do/Don't lists are non-contradictory
- Voice aligns with archetype relationship dynamic
- Core values from SKL-BPV-07 are reflected in language guidelines
- Compute `voice_coherence` score (0-100)

## Output Schema
Write to `node_outputs.bpv_voice_matrix` with keys:
- `voice_dimensions`: `{formality: int, energy: int, warmth: int, authority: int}`
- `channel_matrix`: list of `{channel, formality: int, energy: int, warmth: int, authority: int}`
- `language_guidelines`: `{vocabulary: [], sentence_structure: [], punctuation: [], pronoun_usage: []}`
- `do_list`: list of `{behavior, source_trait, rationale}`
- `dont_list`: list of `{behavior, source_trait, rationale}`
- `voice_coherence`: int (0-100)
- `voice_summary`: str (50-100 word voice description for quick reference)

## Integration Notes
- Downstream consumers: SKL-BPV-10 (character brief includes voice matrix summary), content-agent-service (consumes voice matrix for blog tone)
- `voice_coherence` < 50 triggers an advisory in SKL-BPV-12
- The voice matrix is the most operationally referenced artifact — prioritize clarity and actionability
- Voice matrix is persisted by SKL-BPV-11 for brand context sync to Django
