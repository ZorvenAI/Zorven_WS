---
name: brand-story-channel-narrative-adapter
version: "1.0"
description: Build Claude prompt for channel-specific narrative adaptations across website, social, investor, and press contexts (maps to SKL-BSA-09)
target_agents:
  - brand_story
triggers:
  - "channel narratives"
  - "website about"
  - "social bio"
  - "investor narrative"
  - "press boilerplate"
priority: 10
max_tokens: 500
---

# Channel Narrative Adapter

## Purpose
Construct the channel adaptation section of Claude Call 2 (narrative synthesis). Adapt the core brand story into 4 channel-specific narratives, each with appropriate tone, length, and format.

## Methodology

### 1. Channel Specifications

**Website About** (~300-500 words):
- Warm, inviting tone
- Full origin story arc (condensed)
- Customer-centric framing
- Includes mission/vision

**Social Media Bio** (~150 words):
- Punchy, personality-forward
- Platform-agnostic (works on LinkedIn, Twitter, Instagram)
- Includes brand tagline
- Conversational voice

**Investor Narrative** (~400-600 words):
- Professional, data-aware tone
- Market opportunity framing
- Growth narrative arc
- Includes TAM/SAM/SOM references from market research

**Press Boilerplate** (~200-300 words):
- Formal, factual tone
- Third-person perspective
- Key stats and milestones
- Standard press release format

### 2. Consistency Scoring
- `channel_consistency_score` (0-1): Measures narrative coherence across all 4 channels
- Core brand story elements must be present in all channels despite tone differences

## Output Schema
Contributes to Claude Call 2 prompt. Expected response structure:
- `channel_narratives.website_about`: `{channel, tone, content, word_count}`
- `channel_narratives.social_bio`: `{channel, tone, content, word_count}`
- `channel_narratives.investor`: `{channel, tone, content, word_count}`
- `channel_narratives.press_boilerplate`: `{channel, tone, content, word_count}`
- `channel_narratives.channel_consistency_score`: float (0-1)

## Integration Notes
- Part of Claude Call 2 alongside SKL-BSA-10, SKL-BSA-11, SKL-BSA-12
- Uses cultural narrative insights (SKL-BSA-03) for platform-appropriate cultural references
- Voice matrix (from BPV) guides tone adaptation per channel
