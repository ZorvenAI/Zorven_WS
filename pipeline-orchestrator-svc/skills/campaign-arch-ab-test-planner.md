---
name: campaign-arch-ab-test-planner
version: "1.0"
description: Design A/B test plan with variables, variants, sample sizes, and duration; budget-tiered allocation of 10-20% for testing with minimum 100 conversions per variant (maps to SKL-CAA-09)
target_agents:
  - campaign_architecture
triggers:
  - "ab test"
  - "split test"
  - "test plan"
  - "experiment design"
priority: 10
max_tokens: 500
---

# A/B Test Planner

## Purpose
Design a structured A/B testing plan to validate campaign hypotheses before scaling spend. Determines test variables, variant definitions, required sample sizes, test duration, and budget allocation.

## Methodology

### 1. Test Variable Selection
Prioritize variables by expected impact (test one variable at a time per experiment):

**High Impact** (test first):
- Audience targeting: Different persona segments or interest layers
- Campaign objective: e.g., TRAFFIC vs ENGAGEMENT for MOFU
- Creative concept: Different messaging angles from brand positioning

**Medium Impact**:
- Ad format: Image vs Video vs Carousel
- Placement: Automatic vs Manual placement selection
- Bid strategy: Lowest cost vs Cost cap

**Low Impact** (test later):
- CTA button: Shop Now vs Learn More
- Ad copy length: Short vs Long
- Landing page variant: Different post-click experiences

### 2. Budget Allocation for Testing
Budget-tiered testing allocation:
- **Budget < $50/day**: 20% to testing (limited test capacity, 1 test at a time)
- **Budget $50-200/day**: 15% to testing (2 concurrent tests)
- **Budget > $200/day**: 10% to testing (3+ concurrent tests)

Minimum test ad set budget: $10/day per variant.

### 3. Sample Size Calculation
For statistical significance (95% confidence, 80% power):
- Minimum 100 conversions per variant for conversion-based tests
- Minimum 1,000 clicks per variant for CTR-based tests
- Minimum 10,000 impressions per variant for CPM/reach tests

Estimated test duration based on:
- Daily budget allocated to test
- Expected conversion rate (from benchmarks SKL-CAA-02)
- Minimum 7 days to account for day-of-week variation
- Maximum 28 days (diminishing returns beyond this)

### 4. Test Hypotheses
Generate 2-3 test hypotheses from upstream data:
- Competitor gaps (SKL-CAA-03): "Carousel format will outperform single image because competitors underuse it"
- Audience insights (SKL-CAA-07): "Persona A will outperform Persona B for BOFU conversions"
- RAG learnings (SKL-CAA-05): "Video ads will achieve 30% lower CPA based on prior campaign data"

### 5. Test Execution Rules
Define guardrails:
- Do not end tests early (minimum duration must complete)
- Winner declaration requires statistical significance (p < 0.05)
- If no winner after maximum duration, select variant with lower CPA
- Winning variant gets remaining test budget reallocated to it

## Output Schema
Write to `node_outputs.caa_ab_tests` with keys:
- `test_budget_pct`: float (percentage of total budget allocated to testing)
- `test_budget_daily`: float
- `tests`: list of `{test_id, variable, hypothesis, variants, metric, min_sample_size, estimated_duration_days, daily_budget}`
- `variants`: list of `{variant_id, name, description, targeting_diff}`
- `execution_rules`: dict (min_duration, max_duration, significance_threshold, winner_criteria)
- `test_schedule`: list of `{test_id, start_week, end_week}` (sequential if budget-limited)

## Integration Notes
- Consumed by SKL-CAA-08 (placement budget builder) for test budget reservation
- Consumed by SKL-CAA-10 (blueprint synthesizer) for test ad set specifications
- Test ad sets are included in the campaign blueprint alongside production ad sets
- If total budget is too low for meaningful testing (< $20/day), skip testing and note in warnings
