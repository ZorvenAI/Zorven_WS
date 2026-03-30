---
name: brand-story-mission-vision-refiner
version: "1.0"
description: Build Claude prompt for mission and vision statement generation or refinement, aligned with BPA positioning and BPV personality (maps to SKL-BSA-07)
target_agents:
  - brand_story
triggers:
  - "mission statement"
  - "vision statement"
  - "mission vision"
  - "brand purpose"
priority: 10
max_tokens: 500
---

# Mission/Vision Refiner

## Purpose
Construct the mission and vision statement section of Claude Call 1. If existing statements exist (from Company model), refine them for strategic alignment. If none exist, generate new ones from scratch.

## Methodology

### 1. Mode Detection
- **Refine mode**: Company model has existing mission/vision → improve alignment
- **Generate mode**: No existing statements → create from positioning and personality

### 2. Prompt Construction

**Mission Statement Requirements**:
- Concise (1-2 sentences)
- Action-oriented (what the brand does)
- Audience-inclusive (who benefits)
- Value-anchored (why it matters)
- Score: clarity (0-1), positioning_alignment (0-1), memorability (0-1)

**Vision Statement Requirements**:
- Aspirational (future state)
- Inspiring (motivates stakeholders)
- Achievable (believable trajectory)
- Score: inspiration (0-1), differentiation (0-1), longevity (0-1)

### 3. Alignment Checks
Both statements must:
- Use vocabulary consistent with BPV voice matrix
- Support BPA positioning statement direction
- Reflect brand archetype personality

## Output Schema
Contributes to Claude Call 1 prompt. Expected response structure:
- `mission_vision.mission`: `{current, recommended, scores: {clarity, positioning_alignment, memorability}}`
- `mission_vision.vision`: `{current, recommended, scores: {inspiration, differentiation, longevity}}`
- `mission_vision.mission_scores`: dict
- `mission_vision.vision_scores`: dict

## Integration Notes
- Part of Claude Call 1 alongside SKL-BSA-06 and SKL-BSA-08
- Existing narrative analysis (SKL-BSA-04) informs refine vs. generate mode
