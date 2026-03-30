---
name: brand-naming-competitive-naming
version: "1.0"
description: Analyze competitor naming patterns, identify naming white space, and extract category conventions to inform differentiated name generation (maps to SKL-NTA-03)
target_agents:
  - naming_tagline
triggers:
  - "competitive naming"
  - "competitor names"
  - "naming white space"
  - "category conventions"
  - "naming landscape"
priority: 10
max_tokens: 500
---

# Competitive Naming Analyzer

## Purpose
Analyze the competitive naming landscape from Competitor Intelligence Agent (CIA) outputs to identify naming patterns, category conventions, and white space opportunities. A differentiated name must be distinct from competitor names while remaining recognizable within the category.

## Methodology

### 1. Competitor Intelligence Ingestion
- Read `previous_outputs.competitor_intel` for competitor profiles
- Extract per-competitor: brand name, sub-brand names, product names, taglines, naming patterns
- Read `previous_outputs.discovery` for additional competitive context
- If CIA output is absent, log warning and proceed with limited competitive analysis

### 2. Naming Pattern Classification
Classify each competitor name by pattern:
- **Descriptive**: Name describes the product/service (e.g., "General Electric", "PayPal")
- **Evocative**: Name evokes a feeling or metaphor (e.g., "Amazon", "Nike")
- **Invented**: Coined word with no prior meaning (e.g., "Kodak", "Xerox")
- **Acronym**: Initials or abbreviation (e.g., "IBM", "BMW")
- **Founder**: Named after a person (e.g., "Ford", "Disney")
- **Compound**: Two words combined (e.g., "Facebook", "YouTube")
- **Borrowed**: Word from another language or domain (e.g., "Uber", "Lego")
- Compute pattern frequency distribution across the competitive set

### 3. Category Convention Analysis
Identify naming conventions dominant in the category:
- Common suffixes or prefixes (e.g., "-ly", "-ify", "i-" in tech)
- Typical name length range
- Tone patterns (serious vs. playful)
- Linguistic register (technical vs. accessible)
- Color or nature word frequency

### 4. White Space Identification
Identify naming opportunities not occupied by competitors:
- Underused naming patterns (e.g., if all competitors use descriptive names, evocative is white space)
- Unexplored emotional territories
- Untapped linguistic styles (e.g., short punchy names in a category of long descriptive names)
- Cultural or metaphorical domains not yet claimed

### 5. Collision Risk Assessment
Flag potential naming collisions:
- Names phonetically similar to existing competitor names
- Names that could be confused with category-generic terms
- Names with trademark proximity risk (handled in detail by SKL-NTA-08)

## Output Schema
Write to `node_outputs.nta_competitive_naming` with keys:
- `competitor_names`: list of `{competitor, brand_name, pattern_type, sub_brands: []}`
- `pattern_distribution`: `{descriptive: int, evocative: int, invented: int, acronym: int, founder: int, compound: int, borrowed: int}`
- `category_conventions`: `{common_suffixes: [], common_prefixes: [], avg_name_length: int, dominant_tone: str, linguistic_register: str}`
- `white_space`: list of `{opportunity, pattern_type, emotional_territory, rationale}`
- `collision_risks`: list of `{existing_name, risk_type: "phonetic"|"semantic"|"visual", severity: str}`
- `data_quality`: `{cia_available: bool, discovery_available: bool, competitors_analyzed: int}`

## Integration Notes
- Downstream consumers: SKL-NTA-09 (name generator uses white space as creative direction), SKL-NTA-10 (name scorer penalizes collision risks)
- If CIA output is absent, competitive analysis is limited to discovery-sourced data
- White space recommendations are soft guidance — the name generator may override with strong creative rationale
