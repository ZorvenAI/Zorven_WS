---
name: creative-gen-audience-profiler
version: "1.0"
description: Build per audience x funnel creative profiles specifying visual style, image subjects, emotional tone, color emphasis, and copy approach (maps to SKL-CGA-02)
target_agents:
  - creative_generation
triggers:
  - "audience creative profile"
  - "creative profiling"
  - "audience visual style"
  - "creative brief per audience"
priority: 10
max_tokens: 800
---

# Audience Creative Profiler

## Purpose
Generate detailed creative profiles for each audience-funnel combination defined in the CAA blueprint. Each profile specifies the visual style, image subjects, emotional tone, color emphasis, and copy approach that will guide image prompt construction and copywriting downstream.

## Methodology

### 1. Build Audience x Funnel Matrix
From `node_outputs.cga_context`:
- Extract each audience segment from `audience_profiles`
- Cross with each funnel stage (TOFU, MOFU, BOFU)
- Create one creative profile per intersection (e.g., 3 audiences x 3 stages = 9 profiles)

### 2. Determine Visual Style per Profile
For each audience-funnel pair, select visual direction:
- **TOFU**: Aspirational, lifestyle-oriented, scroll-stopping imagery
- **MOFU**: Product-in-context, benefit-demonstration, social proof visuals
- **BOFU**: Product-focused, urgency cues, trust signals (badges, testimonials)
- Adjust for audience demographics (age, gender, cultural preferences)
- Align with brand personality archetype from WF2

### 3. Select Image Subjects
Define primary and secondary subjects:
- People (demographics matching audience), products, environments, abstract concepts
- Consider competitor creative patterns to differentiate
- Map brand archetype to subject preferences (e.g., Hero = achievement imagery, Caregiver = warm human connection)

### 4. Set Emotional Tone
Map funnel stage to emotional register:
- **TOFU**: Curiosity, aspiration, surprise, delight
- **MOFU**: Trust, empathy, relief, confidence
- **BOFU**: Urgency, certainty, excitement, belonging
- Modulate intensity based on audience psychographics

### 5. Define Color Emphasis
- Primary: Brand palette colors (from `brand_identity.colors`)
- Secondary: Funnel-appropriate accent colors (warm for BOFU urgency, cool for MOFU trust)
- Contrast ratios suitable for Meta ad placements (mobile-first readability)

### 6. Specify Copy Approach
- Tone of voice alignment with brand voice matrix
- Sentence length and complexity matched to audience literacy level
- Language patterns drawn from VoC customer language data
- Funnel-specific messaging angle (awareness, consideration, conversion)

## Output Schema
Write to `node_outputs.cga_audience_profiles` with keys:
- `profiles`: list of profile objects, each containing:
  - `profile_id`: string (UUID)
  - `audience_name`: string
  - `funnel_stage`: "TOFU" | "MOFU" | "BOFU"
  - `visual_style`: string (e.g., "lifestyle-aspirational", "product-demo", "urgency-trust")
  - `image_subjects`: list[str] (primary and secondary subjects)
  - `emotional_tone`: list[str] (1-3 emotions)
  - `color_emphasis`: dict with `primary` and `accent` hex values
  - `copy_approach`: dict with `tone`, `sentence_style`, `messaging_angle`
  - `differentiators`: list[str] (how to stand apart from competitor creatives)
- `matrix_dimensions`: dict with `audiences` count, `funnel_stages` count, `total_profiles` count

## Integration Notes
- Consumed by SKL-CGA-04 (image prompt builder) and SKL-CGA-07/08/09 (copy skills)
- Profile count directly determines the volume of images and copy variants generated
- Keep profiles concise to stay within LLM context limits during downstream generation
- Color emphasis must use the brand palette from SKL-CGA-01 context
