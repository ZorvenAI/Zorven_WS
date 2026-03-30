---
name: brand-naming-social-handle-checker
version: "1.0"
description: Check social media handle availability for name candidates via HTTP HEAD requests across major platforms (maps to SKL-NTA-07)
target_agents:
  - naming_tagline
triggers:
  - "social handle checker"
  - "handle availability"
  - "social media check"
  - "username check"
  - "social handles"
priority: 9
max_tokens: 400
---

# Social Handle Availability Checker

## Purpose
Verify social media handle availability for each name candidate across major platforms. Consistent handle availability across platforms enables unified brand presence and reduces consumer confusion.

## Methodology

### 1. Candidate Collection
- Read `node_outputs.nta_name_candidates` from SKL-NTA-09 for the list of name candidates
- For each candidate, generate handle variations:
  - Exact: `@{name}` (spaces removed, lowercased)
  - Underscored: `@{name_with_underscores}`
  - Dotted: `@{name.with.dots}` (Instagram style)
  - Suffixed: `@{name}official`, `@{name}brand`, `@{name}hq`

### 2. Platform Priority Order
Check handles on platforms in priority order:
1. **Instagram** (`instagram.com/{handle}`)
2. **X/Twitter** (`x.com/{handle}`)
3. **LinkedIn** (`linkedin.com/company/{handle}`)
4. **TikTok** (`tiktok.com/@{handle}`)
5. **YouTube** (`youtube.com/@{handle}`)
6. **Facebook** (`facebook.com/{handle}`)

### 3. HTTP HEAD Check
For each handle variation per platform:
- Send HTTP HEAD request to the platform profile URL
- HTTP 200: mark as `taken`
- HTTP 404: mark as `likely_available`
- HTTP 429 or timeout: mark as `unknown` (rate limited)
- Rate limit: max 3 variations per platform per candidate, max 60 total requests per execution
- Use 2-second delay between requests to the same platform to avoid rate limiting

### 4. Handle Availability Scoring (0-100)
For each candidate, compute a social handle viability score:
- **All 6 platforms exact match available** (100 points)
- **4-5 platforms exact match available** (70 points)
- **2-3 platforms exact match available** (40 points)
- **Only variant handles available** (20 points)
- **No viable handles found** (0 points)
- Bonus: +10 if Instagram and X/Twitter exact matches are both available (highest-impact platforms)

### 5. Recommendation
For each candidate, recommend the best handle strategy:
- Preferred handle (use across all platforms where available)
- Platform-specific alternatives where exact match is taken
- Flag candidates with poor social handle availability

## Output Schema
Write to `node_outputs.nta_social_handles` with keys:
- `handle_results`: list of `{candidate_name, platforms: [{platform, handle_checked, status: "likely_available"|"taken"|"unknown", variation_type}], viability_score: int, recommended_handle: str|null, platform_alternatives: {}}`
- `summary`: `{candidates_checked: int, full_availability: int, partial_availability: int, poor_availability: int}`
- `check_method`: "http_head_heuristic"
- `rate_limit_warnings`: list of str (platforms that returned 429)

## Integration Notes
- Downstream consumers: SKL-NTA-10 (name scorer uses viability_score as a scoring dimension)
- HTTP HEAD checks are heuristic — platforms may return false positives for reserved/suspended accounts
- Handle checking runs concurrently with SKL-NTA-06 (domain checker) for pipeline efficiency
- Rate limiting is critical — aggressive checking can trigger platform-level IP blocks
