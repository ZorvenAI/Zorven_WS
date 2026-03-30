---
name: brand-story-existing-narrative-analyzer
version: "1.0"
description: Analyze existing Company model narrative seeds against BPA/BPV alignment to identify gaps, strengths, and refinement opportunities (maps to SKL-BSA-04)
target_agents:
  - brand_story
triggers:
  - "existing narrative"
  - "narrative gap analysis"
  - "current story analysis"
  - "story alignment"
priority: 10
max_tokens: 500
---

# Existing Narrative Analyzer

## Purpose
Compare the company's existing narrative elements (mission, vision, founding story from Company model) against the strategic direction established by BPA positioning and BPV personality to identify alignment gaps and refinement opportunities.

## Methodology

### 1. Extract Existing Narratives
From Company model context:
- Current mission statement (if any)
- Current vision statement (if any)
- Founding story / about us content
- Existing taglines or slogans

### 2. Alignment Assessment
Score existing narratives against:
- BPA positioning statement (does the story support the positioning?)
- BPV archetype (does the tone match the brand archetype?)
- BPV voice matrix (does vocabulary align with voice guidelines?)
- NTA naming brief (does the narrative support the brand name direction?)

### 3. Gap Analysis
Identify:
- **Strengths**: Elements that already align well with strategy
- **Gaps**: Missing narrative elements or misaligned messaging
- **Conflicts**: Active contradictions between existing story and strategy
- **Opportunities**: Areas where small refinements yield large alignment gains

## Output Schema
Write to `node_outputs.bsa_narrative_analysis` with keys:
- `existing_narratives`: dict of current mission/vision/story content
- `alignment_scores`: dict mapping each element to BPA/BPV alignment score (0-1)
- `gaps`: list of `{element, gap_description, severity: "high"|"medium"|"low"}`
- `strengths`: list of `{element, strength_description}`
- `conflicts`: list of `{element, conflict_description}`
- `refinement_opportunities`: list of `{element, recommendation, expected_impact}`

## Integration Notes
- Feeds into SKL-BSA-07 (Mission/Vision Refiner) for informed refinement vs. generation
- If company has no existing narratives, this skill flags "greenfield" mode for full generation
