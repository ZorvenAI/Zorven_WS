---
name: campaign-arch-audience-targeting-builder
version: "1.0"
description: Convert APA personas into Meta targeting specifications with demographics, interests, behaviors, custom audiences, lookalike audiences, and overlap prevention (maps to SKL-CAA-07)
target_agents:
  - campaign_architecture
triggers:
  - "audience targeting"
  - "meta targeting"
  - "ad targeting"
  - "audience builder"
priority: 10
max_tokens: 600
---

# Audience Targeting Builder

## Purpose
Transform the audience personas from WF1 (APA agent) into concrete Meta Ads targeting specifications for each funnel stage. Includes interest-based targeting, custom audiences, lookalike audiences, and audience exclusion logic.

## Methodology

### 1. Persona-to-Targeting Mapping
For each APA persona (typically 3-5 personas):

**Demographics**:
- Age range: Map persona age brackets to Meta age targeting (18-65+)
- Gender: Map persona gender distribution to targeting (all, male, female)
- Location: Map persona geographic preferences to Meta geo-targeting (country, region, city, radius)
- Language: Map persona language preferences

**Interest Targeting**:
- Map persona psychographic traits to Meta interest categories
- Map persona hobbies and activities to Meta interest keywords
- Layer 2-3 interest categories using AND logic for precision
- Use OR logic within categories for reach

**Behavioral Targeting**:
- Purchase behavior: Map persona buying patterns to Meta purchase behaviors
- Device usage: Map persona tech preferences to device targeting
- Travel patterns: If relevant to brand vertical

### 2. Custom Audience Specifications
If Odoo customer data is available (SKL-CAA-04):

**Customer List Audiences**:
- High-Value segment: Seed for lookalike and retention targeting
- Recent Purchasers: Exclude from acquisition, include in upsell
- Lapsed Customers: Win-back campaign targeting
- Minimum 100 records required per audience

**Website Custom Audiences** (if pixel is configured):
- All visitors (180 days)
- Product page viewers (30 days)
- Cart abandoners (14 days)
- Purchasers (180 days)

### 3. Lookalike Audiences
If custom audiences are viable (>= 1,000 source records):
- 1% lookalike: Highest quality, smallest reach (BOFU)
- 3% lookalike: Balanced quality and reach (MOFU)
- 5% lookalike: Maximum reach, lower precision (TOFU)
- Source: High-Value customer segment preferred

### 4. Audience Exclusions
Prevent audience overlap between funnel stages:
- TOFU: Exclude website visitors (30 days), existing customers
- MOFU: Exclude purchasers (180 days), exclude BOFU custom audiences
- BOFU: Exclude recent purchasers (30 days)
- Retention: Include only existing customers

### 5. Funnel Stage Assignment
Assign audience specs to funnel stages from SKL-CAA-06:
- TOFU: Broad interest targeting + lookalike 5% + competitor exclusions
- MOFU: Layered interest targeting + lookalike 3% + website retargeting
- BOFU: Narrow interest + lookalike 1% + cart abandoners + lead retargeting
- Retention: Custom audience (existing customers) only

## Output Schema
Write to `node_outputs.caa_audience_targeting` with keys:
- `audiences`: list of `{persona_name, funnel_stage, targeting_spec}` where `targeting_spec` contains:
  - `demographics`: dict (age_min, age_max, genders, locations, languages)
  - `interests`: list of `{category, keywords}`
  - `behaviors`: list[str]
  - `custom_audiences`: list of `{name, type, source, min_size}`
  - `lookalike_audiences`: list of `{source, percentage, estimated_reach}`
  - `exclusions`: list of `{audience_name, reason}`
- `estimated_total_reach`: int (deduplicated across all audiences)
- `audience_overlap_risk`: float (0-1)
- `targeting_warnings`: list[str]

## Integration Notes
- Consumed by SKL-CAA-08 (placement budget builder) for ad set audience assignment
- Consumed by SKL-CAA-10 (blueprint synthesizer) for campaign hierarchy
- Competitor audience data from SKL-CAA-03 informs differentiation targeting
- If Odoo data is unavailable, custom/lookalike audiences are omitted (interest-only targeting)
