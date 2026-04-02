---
name: ad-publishing-creative-uploader
version: "1.0"
description: Download CGA-generated images from GCS and upload to Meta as ad images via Marketing API with circuit breaker protection (maps to SKL-APA33-06)
target_agents:
  - ad_publishing
triggers:
  - "upload ad images"
  - "creative upload meta"
  - "image upload marketing api"
  - "ad image transfer"
priority: 6
max_tokens: 700
---

# Creative Uploader

## Purpose
Transfer CGA-generated ad images from Google Cloud Storage to Meta's ad image library via the Marketing API. Handles multiple aspect ratios (1:1, 9:16, 16:9), maps uploaded image hashes back to their corresponding creative packages, and implements a circuit breaker pattern to prevent cascading failures when Meta's upload endpoint is degraded.

## Methodology

### 1. Inventory CGA Creative Assets
From `node_outputs.apa_context.creative_packages`:
- List all image assets with their GCS paths (`gs://bucket/path/image.png`)
- Group by creative package ID and aspect ratio
- Expected ratios: 1:1 (feed), 9:16 (stories/reels), 16:9 (in-stream video covers)
- Validate that each creative package has at least one image asset

### 2. Download Images from GCS
For each image asset:
- Download from GCS using the tenant's service account credentials
- Validate file size (Meta limit: 30MB for images)
- Validate dimensions: minimum 600x600 for 1:1, 1080x1920 for 9:16, 1200x628 for 16:9
- Convert to supported format if needed (JPEG, PNG accepted; WebP requires conversion)
- Store temporarily in `/tmp/apa_{job_id}/` for upload

### 3. Upload to Meta Ad Images API
For each downloaded image, call `POST /act_{ad_account_id}/adimages`:
- Send as multipart form data with `filename` parameter
- On 200 response: extract `images.{filename}.hash` (the ad image hash)
- Map the image hash to: `{creative_package_id, aspect_ratio, original_gcs_path}`
- On 400: log error, skip image, continue with remaining uploads
- On 413 (file too large): attempt JPEG compression at 85% quality, retry once

### 4. Circuit Breaker Protection
Implement circuit breaker with threshold: 5 failures within 60 seconds:
- CLOSED state: normal operation, failures increment counter
- OPEN state: skip remaining uploads, return partial results with `circuit_breaker_tripped: true`
- On trip: set pipeline status to RETRY, include failed images in retry manifest
- Reset counter on each successful upload
- Common failure modes: Meta API rate limiting (error code 17), temporary upload service outage

### 5. Build Image Hash Registry
Create a mapping of image hashes to creative metadata:
- `{image_hash: {creative_package_id, aspect_ratio, dimensions, file_size_bytes, gcs_path}}`
- This registry is consumed by SKL-APA33-07 (ad-assembler) to reference images in ad creative objects

### 6. Cleanup Temporary Files
Remove downloaded images from `/tmp/apa_{job_id}/` after all uploads complete or circuit breaker trips.

## Output Schema
Write to `node_outputs.apa_uploaded_images` with keys:
- `image_registry`: dict mapping image_hash to:
  - `creative_package_id`: string
  - `aspect_ratio`: string (1:1, 9:16, 16:9)
  - `dimensions`: dict (width, height)
  - `file_size_bytes`: int
  - `gcs_source`: string
- `total_uploaded`: int
- `total_failed`: int
- `failed_images`: list[dict] (gcs_path, error_message)
- `circuit_breaker_tripped`: boolean
- `api_calls_made`: int
- `upload_duration_seconds`: float

## Integration Notes
- Image hashes are immutable in Meta; re-uploading the same image bytes returns the same hash, making this operation safely idempotent
- The circuit breaker state is stored in Redis (`apa:circuit:upload:{job_id}`) with 5-minute TTL to persist across potential retries
- Aspect ratio grouping is critical because SKL-APA33-07 assigns images to placements based on ratio (1:1 for feed, 9:16 for stories)
