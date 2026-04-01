---
name: creative-gen-primary-copy-generator
version: "1.0"
description: Generate 2-3 primary copy variants in short, medium, and long formats per audience x funnel with brand voice consistency (maps to SKL-CGA-08)
target_agents:
  - creative_generation
triggers:
  - "primary copy"
  - "ad body copy"
  - "ad text generation"
  - "copy variants"
priority: 10
max_tokens: 800
---

# Primary Copy Generator

## Purpose
Generate 2-3 primary body copy variants for each audience x funnel combination. Each variant is produced in three length formats (short, medium, long) to support different Meta ad placements. Copy builds on the hook (SKL-CGA-07) and leads into the CTA (SKL-CGA-09).

## Methodology

### 1. Load Inputs
From upstream outputs:
- `node_outputs.cga_audience_profiles` -- copy approach, tone, messaging angle
- `node_outputs.cga_hooks` -- generated hooks to extend from
- `node_outputs.cga_context` -- brand identity, value propositions, customer language
- `node_outputs.cga_learnings` -- winning copy patterns (if available)

### 2. Define Length Formats
Three formats per variant to match Meta placement requirements:
- **Short** (40-90 characters): Feed preview text, limited display placements
- **Medium** (90-200 characters): Standard Feed, Marketplace, Search Results
- **Long** (200-500 characters): Detailed Feed copy with full narrative arc

### 3. Generate Copy per Funnel Stage

**TOFU Copy Structure**:
- Expand on hook's curiosity/emotion
- Introduce brand as the solution to the implied need
- Paint a picture of the desired outcome
- Light product mention, heavy on aspiration and relevance

**MOFU Copy Structure**:
- Bridge from pain point to solution
- Present 2-3 key benefits with specificity
- Include social proof element (metrics, testimonials, authority)
- Address top consideration factor for this audience

**BOFU Copy Structure**:
- Reinforce value proposition concisely
- Present the offer clearly (pricing, discount, trial)
- Handle the primary objection
- Create urgency without being manipulative
- Lead naturally into CTA

### 4. Brand Voice Application
For each copy variant:
- Match sentence structure to brand voice matrix (short punchy vs. flowing narrative)
- Use vocabulary consistent with brand personality archetype
- Incorporate 1-2 customer language phrases from VoC data
- Maintain consistent tone across all three length formats

### 5. Variant Differentiation
Ensure 2-3 variants per profile are meaningfully different:
- Variant A: Lead with benefit/outcome
- Variant B: Lead with story/empathy
- Variant C: Lead with data/proof (if applicable)

### 6. Quality Scoring
Rate each variant on:
- **Persuasiveness** (1-5): Does it move the reader toward action?
- **Clarity** (1-5): Is the message immediately understandable?
- **Brand consistency** (1-5): Does it sound like the brand?
- **Length optimization** (1-5): Is each format well-suited to its length?
- Composite score = weighted average

## Output Schema
Write to `node_outputs.cga_primary_copy` with keys:
- `copy_sets`: list of copy set objects, each containing:
  - `audience_name`: string
  - `funnel_stage`: string
  - `profile_id`: string
  - `variants`: list of variant objects, each with:
    - `variant_id`: string (UUID)
    - `variant_label`: "benefit" | "story" | "proof"
    - `short`: string (40-90 chars)
    - `medium`: string (90-200 chars)
    - `long`: string (200-500 chars)
    - `quality_score`: float
- `total_variants`: int
- `avg_quality_score`: float

## Integration Notes
- Copy variants are paired with hooks (SKL-CGA-07) and CTAs (SKL-CGA-09) in SKL-CGA-11
- All copy passes through compliance screening (SKL-CGA-10) before assembly
- Short format is used when image has text overlay; long format for text-primary placements
- Character counts are guidelines; Meta truncation rules vary by placement
