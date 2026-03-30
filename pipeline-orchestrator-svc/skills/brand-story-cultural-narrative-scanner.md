---
name: brand-story-cultural-narrative-scanner
version: "1.0"
description: Scan TCIA cultural trends for narrative-relevant patterns, identifying rising and fading story themes for brand positioning (maps to SKL-BSA-03)
target_agents:
  - brand_story
triggers:
  - "cultural narrative"
  - "trend narratives"
  - "cultural story patterns"
  - "narrative trends"
priority: 10
max_tokens: 500
---

# Cultural Narrative Scanner

## Purpose
Analyze trend and cultural insight data (from TCIA agent) to identify narrative patterns that are rising, stable, or fading. This ensures the brand story aligns with cultural momentum rather than against it.

## Methodology

### 1. Trend Classification
From WF1 context (TCIA trends):
- Classify each scored trend by narrative relevance
- Identify cultural movements that support or conflict with brand positioning

### 2. Narrative Pattern Mapping
Map trends to story archetypes:
- **Rising narratives**: Cultural themes gaining momentum (align brand story here)
- **Stable narratives**: Established cultural truths (safe foundation for messaging)
- **Fading narratives**: Declining cultural themes (avoid or reframe)

### 3. Opportunity Identification
Cross-reference with competitor narrative landscape:
- Identify narrative white space (cultural themes competitors haven't claimed)
- Flag oversaturated narrative territories to avoid

## Output Schema
Write to `node_outputs.bsa_cultural_narratives` with keys:
- `rising`: list of `{theme, relevance_score, narrative_opportunity}`
- `stable`: list of `{theme, relevance_score, foundation_use}`
- `fading`: list of `{theme, relevance_score, avoidance_reason}`
- `narrative_white_space`: list of untapped cultural narrative opportunities
- `recommended_cultural_anchors`: top 3 cultural themes to weave into brand story

## Integration Notes
- Feeds into SKL-BSA-06 (Origin Story) for cultural anchoring
- Feeds into SKL-BSA-09 (Channel Narrative Adapter) for platform-specific cultural tone
- If TCIA data is absent, this skill produces minimal output with reduced cultural alignment
