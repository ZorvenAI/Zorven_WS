---
name: creative-gen-package-synthesizer
version: "1.0"
description: Assemble the full CampaignCreativePackage JSON from all upstream skill outputs with confidence scoring and budget reconciliation (maps to SKL-CGA-12)
target_agents:
  - creative_generation
triggers:
  - "creative package"
  - "package synthesis"
  - "final creative assembly"
  - "campaign creative output"
priority: 10
max_tokens: 800
---

# Package Synthesizer

## Purpose
Assemble all upstream CGA skill outputs into a comprehensive CampaignCreativePackage JSON document. This is the capstone skill that produces the final, structured creative deliverable containing all images, copy, CTAs, and metadata organized by audience x funnel for downstream consumption.

## Methodology

### 1. Collect All Upstream Outputs
Gather from all prior CGA skills:
- SKL-CGA-01: Campaign creative context (completeness score)
- SKL-CGA-02: Audience creative profiles
- SKL-CGA-03: Prior learnings (if available)
- SKL-CGA-04: Image prompts
- SKL-CGA-05: Generated images with GCS paths
- SKL-CGA-07: Hook variants
- SKL-CGA-08: Primary copy variants
- SKL-CGA-09: CTA variants
- SKL-CGA-10: Compliance screening results
- SKL-CGA-11: Assembled creative units with coherence scores

### 2. Build Package Structure
Organize by the CAA blueprint hierarchy:
- **Campaign level**: Group creative units by funnel stage (matching CAA campaigns)
- **Ad set level**: Group by audience segment (matching CAA ad sets)
- **Ad level**: Map assembled creative units to ad briefs from CAA blueprint

### 3. Calculate Confidence Score
Weighted composite across all skill outputs:
- Context completeness (SKL-CGA-01): weight 0.15
- Learnings availability (SKL-CGA-03): weight 0.10
- Image generation success rate (SKL-CGA-05): weight 0.20
- Copy quality average (SKL-CGA-07/08/09): weight 0.20
- Compliance pass rate (SKL-CGA-10): weight 0.15
- Coherence score average (SKL-CGA-11): weight 0.20

### 4. Budget Reconciliation
Summarize creative generation costs:
- Image generation cost (from SKL-CGA-05)
- LLM token cost for copy generation (estimated from token counts)
- Total creative production cost
- Percentage of campaign budget consumed by creative production
- Remaining budget available for ad spend

### 5. Coverage Analysis
Verify creative coverage against CAA blueprint:
- Count of ad briefs with at least one complete creative unit
- Flag any audience x funnel combinations with zero creatives
- Flag ad briefs that exceed the target variant count
- Report coverage percentage (creatives produced / briefs required)

### 6. Generate Package Summary
Human-readable summary including:
- Total images generated across all aspect ratios
- Total copy variants (hooks, primary, CTAs)
- Compliance pass rate
- Average coherence score
- Recommended next steps (launch ready vs. needs human review)

## Output Schema
Write to `node_outputs.cga_package` with keys:
- `package_id`: string (UUID)
- `brand_name`: string
- `blueprint_id`: string (reference to CAA blueprint)
- `campaigns`: list of campaign objects, each containing:
  - `campaign_name`: string
  - `funnel_stage`: string
  - `ad_sets`: list of ad set objects, each containing:
    - `audience_name`: string
    - `ads`: list of ad objects with `creative_units` (from SKL-CGA-11)
- `confidence_score`: float (0-1)
- `confidence_breakdown`: dict with per-skill scores
- `budget_reconciliation`: dict with `image_cost`, `llm_cost`, `total_cost`, `budget_percentage`
- `coverage`: dict with `briefs_required`, `briefs_covered`, `coverage_percentage`, `gaps`
- `compliance_summary`: dict with `total_screened`, `pass_rate`, `blocked_count`
- `summary`: dict with `total_images`, `total_copy_variants`, `avg_coherence`, `recommendation`
- `created_at`: string (ISO 8601)

## Integration Notes
- This is the primary output of the CGA agent pipeline
- Package structure mirrors the CAA blueprint hierarchy for easy downstream mapping
- Consumed by SKL-CGA-13 (persister) for storage and by the Django result handler
- Package JSON is the `result_data` sent via callback to Django
- Coverage gaps should trigger alerts for human creative review
