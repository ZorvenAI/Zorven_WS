---
name: ad-publishing-ad-assembler
version: "1.0"
description: Create ad creatives from uploaded images and CGA copy, assemble ads linking creatives to ad sets in PAUSED status, generate previews (maps to SKL-APA33-07)
target_agents:
  - ad_publishing
triggers:
  - "assemble ads"
  - "create ad creatives"
  - "ad creative assembly"
  - "build meta ads"
priority: 5
max_tokens: 800
---

# Ad Assembler

## Purpose
Create Meta ad creative objects by combining uploaded image hashes with CGA-generated ad copy (headlines, primary text, descriptions, CTAs). Then create ad entities that link each creative to its target ad set, all in PAUSED status. Finally, generate ad preview URLs for the human approval gate in SKL-APA33-08.

## Methodology

### 1. Match Creatives to Ad Sets
For each ad set in `node_outputs.apa_ad_sets.ad_sets`:
- Identify the corresponding creative packages from `node_outputs.apa_context.creative_packages`
- Match by audience segment name and funnel stage
- Select appropriate image hashes from `node_outputs.apa_uploaded_images.image_registry` by aspect ratio:
  - Feed placements: prefer 1:1 images
  - Stories/Reels placements: prefer 9:16 images
  - In-stream placements: prefer 16:9 images

### 2. Create Ad Creative Objects
For each creative-to-ad-set pairing, call `POST /act_{ad_account_id}/adcreatives`:
- `name`: `{brand_name} - {segment} - {funnel_stage} - Creative {n}`
- `object_story_spec`: dict containing:
  - `page_id`: from `node_outputs.apa_account_validation.page_id`
  - `link_data` (for link ads):
    - `image_hash`: from uploaded image registry
    - `link`: landing page URL from CAA blueprint
    - `message`: CGA primary text
    - `name`: CGA headline (25 char recommended)
    - `description`: CGA description
    - `call_to_action`: `{type: "LEARN_MORE" | "SHOP_NOW" | "SIGN_UP" | "CONTACT_US", value: {link: "..."}}`
  - `video_data` (for video/carousel, if applicable)
- `asset_feed_spec` (for dynamic creative):
  - `images`: list of `{hash: image_hash}` for multi-image testing
  - `bodies`: list of `{text: primary_text_variant}` for copy testing
  - `titles`: list of `{text: headline_variant}`
  - `descriptions`: list of `{text: description_variant}`
  - `call_to_action_types`: list of CTA options

### 3. Create Ad Entities
For each creative object, call `POST /act_{ad_account_id}/ads`:
- `name`: `{brand_name} - {segment} - Ad {n}`
- `adset_id`: the target ad set ID
- `creative`: `{creative_id: created_creative_id}`
- `status`: `PAUSED` (never ACTIVE at this stage)
- `tracking_specs`: UTM parameters for attribution tracking
  - `utm_source=meta`, `utm_medium=paid`, `utm_campaign={campaign_name}`, `utm_content={ad_name}`

### 4. Generate Ad Previews
For each created ad, call `GET /{ad_id}/previews?ad_format=DESKTOP_FEED_STANDARD,MOBILE_FEED_STANDARD,INSTAGRAM_STANDARD,INSTAGRAM_STORY`:
- Extract preview iframe URLs for each format
- Store preview HTML/URLs for the approval UI
- Generate a summary preview card with: image thumbnail, headline, primary text, CTA button

### 5. Register Entities for Rollback
Append all created entities to the rollback registry:
- `{entity_type: "adcreative", entity_id: creative_id, parent_adset_id}`
- `{entity_type: "ad", entity_id: ad_id, parent_adset_id, creative_id}`
- Rollback order: delete ads first, then creatives, then ad sets, then campaign

## Output Schema
Write to `node_outputs.apa_ads` with keys:
- `ads`: list[dict] each containing:
  - `ad_id`: string
  - `ad_name`: string
  - `creative_id`: string
  - `adset_id`: string
  - `image_hash`: string
  - `headline`: string
  - `primary_text`: string (truncated to 125 chars for preview)
  - `cta_type`: string
  - `status`: string (PAUSED)
  - `preview_urls`: dict (desktop_feed, mobile_feed, instagram, instagram_story)
- `total_ads_created`: int
- `total_creatives_created`: int
- `rollback_registry`: list[dict] (updated with all entities)
- `preview_summary`: list[dict] (ad_id, thumbnail, headline, cta -- for approval UI)

## Integration Notes
- Ad previews are temporary and expire after 24 hours; the approval gate (SKL-APA33-08) must be completed within this window
- Dynamic creative optimization (asset_feed_spec) is preferred when multiple copy variants exist, as Meta automatically tests combinations
- The rollback registry now contains the complete entity tree (campaign -> ad sets -> creatives -> ads) enabling full atomic rollback
