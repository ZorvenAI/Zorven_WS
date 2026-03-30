---
name: brand-story-narrative-synthesizer
version: "1.0"
description: Capstone synthesis skill that assembles all narrative artifacts into a final narrative package with confidence scoring, alignment verification, and WF2 strategy summary (maps to SKL-BSA-12)
target_agents:
  - brand_story
triggers:
  - "narrative synthesis"
  - "narrative package"
  - "final narrative"
  - "brand narrative assembly"
priority: 10
max_tokens: 600
---

# Brand Narrative Synthesizer

## Purpose
Assemble all generated narrative artifacts (origin story, mission/vision, pitches, channel narratives, style guide, sub-brand stories) into a coherent final narrative package. Calculate overall confidence and alignment scores. Produce the WF2 Strategy Complete Summary.

## Methodology

### 1. Artifact Collection
Gather all outputs from Claude Call 1 and Claude Call 2:
- Origin story (3 versions) with quality scores
- Mission/Vision statements with alignment scores
- Elevator pitches (15s/30s/60s) with memorability scores
- Channel narratives (4 channels) with consistency score
- Story style guide
- Sub-brand story variations (if BAA data available)

### 2. Cross-Artifact Validation
Verify consistency across all artifacts:
- Archetype expression consistency (same archetype voice across all pieces)
- Positioning alignment (all artifacts support the same positioning)
- Vocabulary consistency (voice matrix compliance across all text)
- Emotional arc coherence (tension→transformation→resolution present)

### 3. Confidence Calculation
Overall confidence = weighted average of:
- Origin story quality scores (30%)
- Mission/Vision alignment scores (20%)
- Pitch memorability (15%)
- Channel consistency (15%)
- Cross-artifact validation (20%)

### 4. WF2 Strategy Complete Summary
If all WF2 agents have completed, generate a capstone summary:
- BPA: Positioning statement + key differentiators
- BAA: Architecture model + hierarchy overview
- BPV: Primary archetype + voice summary
- NTA: Recommended name + tagline
- BSA: Origin story (short version) + mission + 30s pitch

## Output Schema
Write to `node_outputs.bsa_narrative_package` with keys:
- `narrative_package`: `{overall_confidence, positioning_narrative_alignment, archetype_consistency, summary}`
- `wf2_strategy_summary`: dict (positioning, architecture, personality, naming, story highlights)
- `confidence_score`: float (0-1)
- `validation_results`: dict of cross-artifact checks

## Integration Notes
- This is the final synthesis step before persistence (SKL-BSA-13)
- The WF2 strategy summary is only complete when all 5 WF2 agents have run
- If confidence < 0.7, triggers SKL-BSA-14 (Human Escalation)
