---
name: brand-story-elevator-pitch-generator
version: "1.0"
description: Build Claude prompt for elevator pitch generation in 3 durations (15s/30s/60s at 150 wpm) with memorability and clarity scoring (maps to SKL-BSA-08)
target_agents:
  - brand_story
triggers:
  - "elevator pitch"
  - "brand pitch"
  - "30 second pitch"
  - "pitch generation"
priority: 10
max_tokens: 500
---

# Elevator Pitch Generator

## Purpose
Construct the elevator pitch section of Claude Call 1. Generate pitches at three durations (15-second, 30-second, 60-second) calibrated to 150 words-per-minute speaking rate.

## Methodology

### 1. Duration Calibration
- **15s pitch** (~38 words): Hook + value proposition
- **30s pitch** (~75 words): Hook + problem + solution + differentiator
- **60s pitch** (~150 words): Full narrative arc: hook + problem + solution + differentiator + proof + call to action

### 2. Prompt Construction
Each pitch must:
- Open with an attention-grabbing hook (emotional or provocative)
- Include the brand name and recommended tagline (from NTA)
- Reflect the brand archetype voice (from BPV)
- Support the positioning statement (from BPA)
- End with a memorable closing line

### 3. Quality Criteria
Each pitch scored on:
- `memorability_score` (0-1): Hook strength, closing impact, rhythm
- `clarity_score` (0-1): Message comprehension on first hearing
- `word_count`: Must be within 10% of target

## Output Schema
Contributes to Claude Call 1 prompt. Expected response structure:
- `pitches.pitch_15s`: `{duration_label, word_count, content, memorability_score, clarity_score}`
- `pitches.pitch_30s`: `{duration_label, word_count, content, memorability_score, clarity_score}`
- `pitches.pitch_60s`: `{duration_label, word_count, content, memorability_score, clarity_score}`

## Integration Notes
- Part of Claude Call 1 alongside SKL-BSA-06 and SKL-BSA-07
- Pitches should be derivative of the origin story emotional arc
- 30s pitch is the "hero" version used for primary scoring in analytics
