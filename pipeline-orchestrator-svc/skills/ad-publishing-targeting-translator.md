---
name: ad-publishing-targeting-translator
version: "1.0"
description: Use Claude Sonnet 4 to translate APA persona demographics and interests into Meta targeting spec JSON with Special Ad Category handling (maps to SKL-APA33-05)
target_agents:
  - ad_publishing
triggers:
  - "translate targeting"
  - "persona to targeting spec"
  - "meta targeting translation"
  - "audience targeting mapping"
priority: 7
max_tokens: 1000
---

# Targeting Translator

## Purpose
Translate human-readable audience persona profiles from the Audience Persona Agent into machine-readable Meta Marketing API targeting specification JSON. Uses Claude Sonnet 4 for intelligent mapping of psychographic and behavioral attributes to Meta's interest and behavior taxonomy, with a rule-based fallback when the LLM is unavailable. Handles Special Ad Category restrictions that limit available targeting parameters.

## Methodology

### 1. Extract Persona Targeting Attributes
For each audience persona in `node_outputs.apa_context.audience_personas`:
- Demographics: age range, gender distribution, education level, income bracket
- Geographic: countries, regions/states, cities, radius targeting
- Interests: hobbies, media consumption, brand affinities, topics
- Behaviors: purchase behavior, device usage, travel patterns, digital activity
- Custom audiences: lookalike source, website visitor segments (if available)

### 2. Resolve Meta Interest and Behavior IDs
Use Claude Sonnet 4 to map persona attributes to Meta's targeting taxonomy:
- Prompt the LLM with the persona profile and Meta's interest category structure
- Request structured JSON output with Meta interest IDs and names
- Example mapping: persona interest "fitness enthusiasts" -> Meta interest `{id: 6003139266461, name: "Physical fitness"}`
- For behaviors: "frequent online shoppers" -> Meta behavior `{id: 6002714895372, name: "Engaged Shoppers"}`
- Validate returned IDs against Meta's `GET /search?type=adinterest&q={query}` endpoint

### 3. Construct Meta Targeting Spec JSON
Build the targeting specification object:
```json
{
  "geo_locations": {
    "countries": ["US"],
    "regions": [{"key": "3847"}],
    "cities": [{"key": "2420379", "radius": 25, "distance_unit": "mile"}]
  },
  "age_min": 25,
  "age_max": 54,
  "genders": [1, 2],
  "interests": [{"id": "6003139266461", "name": "Physical fitness"}],
  "behaviors": [{"id": "6002714895372", "name": "Engaged Shoppers"}],
  "flexible_spec": [
    {
      "interests": [...],
      "behaviors": [...]
    }
  ],
  "exclusions": {
    "interests": [...]
  },
  "publisher_platforms": ["facebook", "instagram"],
  "device_platforms": ["mobile", "desktop"]
}
```

### 4. Apply Special Ad Category Restrictions
When `apa_context.special_ad_category` is HOUSING, CREDIT, or EMPLOYMENT:
- Remove `age_min` and `age_max` fields entirely
- Remove `genders` field entirely
- Replace ZIP code and radius targeting with country + state only
- Remove restricted interest categories (e.g., multicultural affinity segments)
- Remove restricted behavior categories
- Set minimum reach radius to 15 miles (Meta requirement for housing)
- Log all restrictions applied for audit trail

### 5. Rule-Based Fallback
When Claude Sonnet 4 is unavailable (timeout, API error, rate limit):
- Use a static mapping table of common persona attributes to Meta interest IDs
- Map age ranges directly to `age_min`/`age_max` (18-24, 25-34, 35-44, 45-54, 55-64, 65+)
- Map gender descriptions to Meta codes (male=1, female=2, all=[1,2])
- Map country names to ISO 3166-1 alpha-2 codes
- Use broad interest categories from a curated fallback dictionary (~200 common mappings)
- Flag the output as `llm_assisted: false` for quality tracking

### 6. Validate Targeting Spec
Before returning:
- Verify `geo_locations` contains at least one country
- Verify `age_min >= 18` and `age_max <= 65` (Meta policy)
- Confirm estimated audience size is not too narrow (Meta minimum ~1,000 people)
- Call Meta's `GET /act_{id}/reachestimate` with the targeting spec to get estimated daily reach

## Output Schema
Write to `node_outputs.apa_targeting` with keys:
- `targeting_specs`: list[dict] each containing:
  - `persona_id`: string
  - `persona_name`: string
  - `targeting_spec`: dict (the Meta-compatible JSON targeting object)
  - `estimated_reach`: dict (estimate_dau, estimate_mau) or null
  - `llm_assisted`: boolean
  - `restrictions_applied`: list[str] (Special Ad Category restrictions)
- `special_ad_category`: string | null
- `fallback_used`: boolean
- `interest_ids_resolved`: int
- `behavior_ids_resolved`: int
- `validation_passed`: boolean
- `validation_warnings`: list[str]

## Integration Notes
- The translated targeting specs are consumed by SKL-APA33-04 (ad-set-creator) for the `targeting` field in the ad set creation payload
- Interest and behavior ID resolution is cached in Redis (24h TTL) to avoid redundant Meta API search calls across pipeline runs
- When the LLM fallback is used, the `completeness_score` in the final output is penalized by 0.15 to reflect reduced targeting precision
