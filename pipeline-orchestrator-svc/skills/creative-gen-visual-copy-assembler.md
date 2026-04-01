---
name: creative-gen-visual-copy-assembler
version: "1.0"
description: Pair generated images with compliant copy and CTAs, evaluate image-copy coherence, and produce ranked ad creative combinations (maps to SKL-CGA-11)
target_agents:
  - creative_generation
triggers:
  - "assemble creatives"
  - "pair images with copy"
  - "creative assembly"
  - "ad combination"
priority: 10
max_tokens: 800
---

# Visual-Copy Assembler

## Purpose
Pair generated images with compliant hooks, primary copy, and CTAs into complete ad creative combinations. Evaluate the coherence between visual and textual elements, rank combinations by predicted effectiveness, and produce the assembled creative units ready for packaging.

## Methodology

### 1. Load All Creative Elements
From upstream outputs:
- `node_outputs.cga_images` -- generated images with GCS paths and metadata
- `node_outputs.cga_hooks` -- hook variants with quality scores
- `node_outputs.cga_primary_copy` -- primary copy variants (short/medium/long)
- `node_outputs.cga_ctas` -- CTA variants with button enums
- `node_outputs.cga_compliance` -- compliance screening results

### 2. Filter Compliant Elements
- Exclude any copy element with compliance status "fail" (unless a compliant alternative is available)
- Substitute compliant alternatives where auto-substitution is enabled
- Log excluded elements for the audit trail

### 3. Match by Audience x Funnel
Group elements by their shared `profile_id` (audience x funnel):
- Images belonging to this profile
- Hooks belonging to this profile
- Primary copy belonging to this profile
- CTAs belonging to this profile

### 4. Generate Combinations
For each profile, create ranked combinations:
- Pair each image (per aspect ratio) with each hook + copy + CTA combination
- Apply combinatorial pruning: top N combinations per profile (cap at 6-9)
- Prefer combinations where hook technique and image emotional tone align

### 5. Evaluate Image-Copy Coherence
Score each combination on visual-textual alignment:
- **Emotional consistency** (1-5): Does the image mood match the copy tone?
- **Subject relevance** (1-5): Does the image subject relate to the copy message?
- **Color harmony** (1-5): Do image colors complement text overlay readability?
- **Placement fit** (1-5): Does the aspect ratio suit the intended Meta placement?
- Coherence score = average of the four dimensions

### 6. Rank Combinations
Produce a ranked list per profile:
- Primary sort: coherence score (descending)
- Secondary sort: average quality score across hook + copy + CTA
- Tertiary sort: copy length variant (prefer medium for default)
- Mark top combination as "recommended" per profile

### 7. Assemble Creative Units
For each selected combination, produce a complete creative unit:
- Image reference (GCS path, signed URL, aspect ratio)
- Hook text
- Primary copy (all three length variants)
- CTA button enum + CTA text
- Placement recommendations based on aspect ratio
- Text overlay zone coordinates (from image prompt composition notes)

## Output Schema
Write to `node_outputs.cga_assembled` with keys:
- `creative_units`: list of unit objects, each containing:
  - `unit_id`: string (UUID)
  - `profile_id`: string
  - `audience_name`: string
  - `funnel_stage`: string
  - `image`: dict with `image_id`, `gcs_path`, `signed_url`, `aspect_ratio`
  - `hook`: dict with `hook_text`, `technique`
  - `primary_copy`: dict with `short`, `medium`, `long`, `variant_label`
  - `cta`: dict with `button_enum`, `cta_text`
  - `coherence_score`: float
  - `combined_quality_score`: float
  - `is_recommended`: boolean
  - `placement_recommendations`: list[str]
- `total_units`: int
- `units_per_profile`: dict keyed by profile_id with count
- `excluded_elements`: list of `{element_id, reason}`

## Integration Notes
- This skill produces the creative units consumed by SKL-CGA-12 (package synthesizer)
- Coherence evaluation is heuristic-based, not vision-model-based in v1
- Recommended units are prioritized in the final package for initial campaign launch
- Non-recommended variants serve as A/B test alternatives
- Text overlay coordinates enable downstream design tools to place copy on images
