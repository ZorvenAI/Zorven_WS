---
name: creative-gen-image-generator
version: "1.0"
description: Execute Nano Banana 2 image generation for all prompts across 3 aspect ratios with retry logic, circuit breaker, GCS upload, and cost tracking (maps to SKL-CGA-05)
target_agents:
  - creative_generation
triggers:
  - "generate images"
  - "image generation"
  - "create ad images"
  - "produce visuals"
priority: 10
max_tokens: 800
---

# Image Generator

## Purpose
Execute all image generation prompts from SKL-CGA-04 against the Nano Banana 2 model. Handle retries, circuit breaking on sustained failures, upload generated images to GCS, and track per-image cost for budget reconciliation.

## Methodology

### 1. Load Prompts
From `node_outputs.cga_image_prompts`:
- Read all prompt objects with their aspect ratio variants
- Calculate total generation count (prompts x aspect ratios)
- Estimate total cost based on per-image pricing

### 2. Execute Image Generation
For each prompt and aspect ratio combination:
- Call Nano Banana 2 API with prompt text, negative prompt, dimensions, and quality setting
- Set generation timeout at 60 seconds per image
- Capture generation metadata (model version, seed used, inference time)

### 3. Retry Logic
On generation failure:
- **Transient errors (429, 500, 502, 503)**: Retry up to 3 times with exponential backoff (2s, 4s, 8s)
- **Content policy rejection (400)**: Log rejection reason, skip prompt, flag for review
- **Timeout**: Retry once with reduced quality setting

### 4. Circuit Breaker
Protect against sustained API failures:
- Track failure count within a rolling 60-second window
- **Open circuit** after 5 consecutive failures: pause generation for 30 seconds
- **Half-open**: Attempt single request after cooldown
- **Close circuit**: Resume normal operation after 2 consecutive successes
- If circuit remains open after 3 cooldown cycles, fail the skill with partial results

### 5. GCS Upload
For each successfully generated image:
- Upload to `{gcs_raw_bucket}/creative/{context_id}/{prompt_id}/{aspect_ratio}.png`
- Set content type to `image/png`
- Generate signed URL with 7-day expiry for preview
- Record GCS path and signed URL in output metadata

### 6. Cost Tracking
Track generation costs:
- Per-image cost based on resolution and quality tier
- Running total across all generations
- Compare against campaign budget allocation from CAA blueprint
- Flag if creative generation cost exceeds 5% of total campaign budget

### 7. Progress Reporting
Send incremental progress callbacks:
- Report completion percentage as images are generated
- Include count of successful, failed, and skipped generations

## Output Schema
Write to `node_outputs.cga_images` with keys:
- `images`: list of image objects, each containing:
  - `image_id`: string (UUID)
  - `prompt_id`: string (reference to source prompt)
  - `audience_name`: string
  - `funnel_stage`: string
  - `aspect_ratio`: string
  - `width`: int
  - `height`: int
  - `gcs_path`: string
  - `signed_url`: string
  - `generation_time_ms`: int
  - `seed_used`: int
  - `quality_tier`: string
- `generation_summary`: dict with `total_attempted`, `successful`, `failed`, `skipped`, `circuit_breaker_trips`
- `cost_summary`: dict with `per_image_cost`, `total_cost`, `budget_percentage`
- `failed_prompts`: list of `{prompt_id, reason, retries_attempted}`

## Integration Notes
- This is the most resource-intensive skill; monitor for cost overruns
- Circuit breaker state is ephemeral (not persisted to Redis)
- GCS paths follow tenant isolation: `{tenant_bucket}/creative/...`
- Signed URLs are consumed by SKL-CGA-11 (visual-copy assembler) for pairing
- Partial results are acceptable; downstream skills handle missing images gracefully
- Cost data feeds into SKL-CGA-12 (package synthesizer) for budget reporting
