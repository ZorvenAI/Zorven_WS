---
name: creative-gen-cta-generator
version: "1.0"
description: Generate 2-3 CTA variants per audience x funnel using Meta CTA button enum values with supporting CTA copy (maps to SKL-CGA-09)
target_agents:
  - creative_generation
triggers:
  - "call to action"
  - "CTA generation"
  - "CTA variants"
  - "ad button text"
priority: 10
max_tokens: 800
---

# CTA Generator

## Purpose
Generate 2-3 call-to-action variants for each audience x funnel combination. Each variant pairs a Meta Ads CTA button enum value with supporting CTA copy text. CTAs are calibrated to funnel stage intent and audience readiness to act.

## Methodology

### 1. Load Inputs
From upstream outputs:
- `node_outputs.cga_audience_profiles` -- messaging angle, funnel stage
- `node_outputs.cga_context` -- brand identity, offer details
- `node_outputs.cga_primary_copy` -- body copy variants to align with

### 2. Map Funnel Stage to Meta CTA Buttons
Select appropriate CTA button values from Meta's enum:

**TOFU (Awareness)**:
- `LEARN_MORE` -- default awareness CTA
- `WATCH_MORE` -- video content
- `SEE_MENU` -- restaurant/food brands
- `LISTEN_NOW` -- audio/podcast brands

**MOFU (Consideration)**:
- `SIGN_UP` -- newsletter, free resource
- `DOWNLOAD` -- lead magnet, app
- `GET_QUOTE` -- services, B2B
- `CONTACT_US` -- consultation-based
- `SEND_MESSAGE` -- Messenger engagement

**BOFU (Conversion)**:
- `SHOP_NOW` -- e-commerce direct purchase
- `BUY_NOW` -- limited offer
- `BOOK_NOW` -- appointments, reservations
- `GET_OFFER` -- discount/promotion
- `ORDER_NOW` -- food delivery, subscriptions
- `SUBSCRIBE` -- recurring products/services

### 3. Generate CTA Copy Text
For each CTA button, write supporting text (the line immediately before or around the button):
- Keep under 30 characters for inline display
- Reinforce urgency (BOFU) or curiosity (TOFU) from hook
- Include specificity where possible ("Get your free guide" vs. "Download")
- Match brand voice from personality data

### 4. Variant Strategy
Generate 2-3 CTA variants per profile:
- **Variant A**: Standard best-practice CTA for the funnel stage
- **Variant B**: Higher-urgency or more specific alternative
- **Variant C** (optional): Soft CTA for lower-commitment audiences

### 5. CTA-Copy Coherence Check
Verify each CTA makes logical sense with the primary copy:
- TOFU copy should not pair with `SHOP_NOW`
- BOFU copy should not pair with `LEARN_MORE`
- Ensure the CTA button matches the landing page action

### 6. Quality Scoring
Rate each CTA variant:
- **Action clarity** (1-5): Is the next step obvious?
- **Funnel alignment** (1-5): Does urgency match the stage?
- **Brand voice** (1-5): Does it sound like the brand?

## Output Schema
Write to `node_outputs.cga_ctas` with keys:
- `cta_sets`: list of CTA set objects, each containing:
  - `audience_name`: string
  - `funnel_stage`: string
  - `profile_id`: string
  - `variants`: list of CTA objects, each with:
    - `cta_id`: string (UUID)
    - `button_enum`: string (Meta CTA button value)
    - `cta_text`: string (supporting copy text)
    - `urgency_level`: "low" | "medium" | "high"
    - `quality_score`: float
- `total_ctas`: int

## Integration Notes
- CTA button enum values must match Meta Marketing API exactly
- CTAs are assembled with hooks and primary copy in SKL-CGA-11
- CTA text undergoes compliance screening in SKL-CGA-10
- Landing page URL is not generated here; it comes from the CAA blueprint ad brief
- Multiple CTA variants support A/B testing defined in CAA blueprint
