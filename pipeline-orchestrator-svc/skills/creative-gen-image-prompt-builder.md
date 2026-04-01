---
name: creative-gen-image-prompt-builder
version: "1.0"
description: Construct AI image generation prompts from creative profiles and brand visual context for each audience x funnel combination (maps to SKL-CGA-04)
target_agents:
  - creative_generation
triggers:
  - "image prompt"
  - "image generation prompt"
  - "visual prompt"
  - "creative image brief"
priority: 10
max_tokens: 800
---

# Image Prompt Builder

## Purpose
Transform audience creative profiles from SKL-CGA-02 into structured AI image generation prompts. Each prompt encodes visual style, subjects, mood, color palette, composition, and brand constraints in a format optimized for the Nano Banana 2 image generation model.

## Methodology

### 1. Load Creative Profiles
From `node_outputs.cga_audience_profiles`:
- Iterate each audience x funnel profile
- Extract visual style, image subjects, emotional tone, color emphasis
- Cross-reference with brand identity from `node_outputs.cga_context`

### 2. Build Base Prompt Structure
For each profile, construct a prompt with these components:
- **Subject**: Primary subject(s) from profile (people, products, scenes)
- **Setting/Environment**: Context appropriate to audience and funnel stage
- **Style directive**: Photography style, illustration style, or graphic design style
- **Mood/Lighting**: Mapped from emotional tone (e.g., warm golden hour for trust, high contrast for urgency)
- **Color directive**: Brand primary + accent colors as explicit color instructions
- **Composition**: Rule of thirds, centered, negative space for text overlay zones
- **Exclusions**: Negative prompt elements (competitor visual cues, off-brand elements)

### 3. Apply Brand Constraints
Enforce brand visual identity:
- Color palette adherence (primary, secondary, accent from brand guidelines)
- Typography style hints (modern, classic, bold) for any text-in-image needs
- Brand archetype visual language (e.g., Explorer = open landscapes, Ruler = structured symmetry)
- Industry-appropriate imagery (avoid regulated content for healthcare, finance)

### 4. Apply Learnings Overlay
If `node_outputs.cga_learnings.learnings_available` is true:
- Boost elements from winning patterns
- Exclude elements from losing patterns
- Adjust style based on format preferences

### 5. Generate Aspect Ratio Variants
For each prompt, create 3 aspect ratio specifications:
- **1:1** (1080x1080): Instagram Feed, Facebook Feed
- **9:16** (1080x1920): Stories, Reels
- **1.91:1** (1200x628): Facebook/Instagram horizontal placements
- Adjust composition directives per aspect ratio (text safe zones differ)

### 6. Add Technical Parameters
Append generation parameters:
- Resolution targets per aspect ratio
- Quality setting (high for hero images, standard for variants)
- Seed value strategy (fixed seed for consistency across aspect ratios)

## Output Schema
Write to `node_outputs.cga_image_prompts` with keys:
- `prompts`: list of prompt objects, each containing:
  - `prompt_id`: string (UUID)
  - `profile_id`: string (reference to audience profile)
  - `audience_name`: string
  - `funnel_stage`: string
  - `prompt_text`: string (the full generation prompt)
  - `negative_prompt`: string (exclusions)
  - `aspect_ratios`: list of `{ratio, width, height, composition_notes}`
  - `style_parameters`: dict with quality, seed strategy
  - `brand_constraints_applied`: list[str]
- `total_prompts`: int
- `total_images_planned`: int (prompts x aspect ratios)

## Integration Notes
- Consumed directly by SKL-CGA-05 (image generator) which executes the prompts
- Prompt quality directly impacts image quality; iterate prompts before generation
- Keep prompts under 500 tokens each for optimal Nano Banana 2 performance
- Text overlay zones in composition notes are used by SKL-CGA-11 (visual-copy assembler)
