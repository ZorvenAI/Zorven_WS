---
name: brand-story-style-guide-builder
version: "1.0"
description: Build Claude prompt for story style guide generation including narrative principles, approved/forbidden themes, tone guidelines, and story examples (maps to SKL-BSA-10)
target_agents:
  - brand_story
triggers:
  - "story style guide"
  - "narrative guidelines"
  - "storytelling guide"
  - "narrative principles"
priority: 10
max_tokens: 500
---

# Story Style Guide Builder

## Purpose
Construct the story style guide section of Claude Call 2. Produce actionable guidelines for maintaining narrative consistency across all brand communications.

## Methodology

### 1. Narrative Principles
Derive 5-7 core storytelling principles from:
- Brand archetype narrative patterns (from BPV)
- Positioning differentiation strategy (from BPA)
- Emotional arc structure (from SKL-BSA-02)

### 2. Theme Curation

**Approved Themes**:
- Rising cultural narratives (from SKL-BSA-03)
- Brand value-aligned topics
- Archetype-consistent metaphor domains

**Forbidden Themes**:
- Fading cultural narratives
- Competitor-saturated narrative territories (from SKL-BSA-05)
- Brand value anti-associations

### 3. Tone Guidelines
Channel-specific tone parameters:
- Formality spectrum position
- Humor appropriateness level
- Emotional intensity range
- Vocabulary do's and don'ts (aligned with BPV voice matrix)

### 4. Story Examples
2-3 illustrative examples per context:
- Customer success story template
- Product/service narrative template
- Social media storytelling template

## Output Schema
Contributes to Claude Call 2 prompt. Expected response structure:
- `story_style_guide.narrative_principles`: list[str]
- `story_style_guide.approved_themes`: list[str]
- `story_style_guide.forbidden_themes`: list[str]
- `story_style_guide.tone_guidelines`: dict (channel -> guidelines)
- `story_style_guide.story_examples`: list of `{context, example}`

## Integration Notes
- Part of Claude Call 2 alongside SKL-BSA-09, SKL-BSA-11, SKL-BSA-12
- Extends (not replaces) the BPV voice matrix — focuses on narrative-specific guidance
