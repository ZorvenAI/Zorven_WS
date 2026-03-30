---
name: brand-naming-tagline-synthesizer
version: "1.0"
description: Build structured Claude prompt for tagline generation paired with top-scoring name candidates, incorporating positioning and voice constraints (maps to SKL-NTA-11)
target_agents:
  - naming_tagline
triggers:
  - "tagline synthesizer"
  - "generate taglines"
  - "tagline creation"
  - "slogan generation"
  - "brand tagline"
priority: 9
max_tokens: 500
---

# Tagline Synthesizer

## Purpose
Construct a structured Claude prompt to generate 3-5 tagline candidates for each recommended-tier name. Taglines must complement the name, reinforce the positioning statement, and resonate with the audience's emotional expectations. The tagline is the verbal distillation of the brand promise.

## Methodology

### 1. Input Assembly
Collect upstream skill outputs:
- SKL-NTA-10 `nta_name_scores`: Scored and ranked name candidates (required — use recommended tier)
- SKL-NTA-01 `nta_brand_context`: Positioning statement and differentiators (required)
- SKL-NTA-02 `nta_audience_psychology`: Audience tone and emotional targets (enriching)
- SKL-NTA-04 `nta_identity_seed`: Voice constraints and personality style (enriching)
- SKL-NTA-03 `nta_competitive_naming`: Competitor taglines to differentiate from (enriching)

### 2. Tagline Brief Construction
For each recommended-tier name, build a tagline brief:

**Brand Context**:
- Name and its rationale (why this name was chosen)
- Positioning statement: the core brand promise
- Key differentiators: what sets the brand apart
- Value proposition: the benefit to the customer

**Voice Constraints**:
- Formality level from voice matrix (from SKL-NTA-04)
- Humor tolerance (can the tagline be witty or must it be serious?)
- Language register (technical vs. accessible)
- Do/don't list applicable to taglines

**Audience Fit**:
- Tone preferences from audience psychology (from SKL-NTA-02)
- Emotional targets the tagline should reinforce
- Vocabulary level appropriate for the audience

**Competitive Differentiation**:
- Competitor taglines to avoid similarity (from SKL-NTA-03)
- Category tagline conventions (to follow or subvert)

### 3. Prompt Output Requirements
The Claude prompt requests for each name:
- Generate 3-5 tagline candidates
- For each tagline provide: tagline text, tagline type (aspirational/descriptive/imperative/provocative/metaphorical), character count, rationale, intended emotional impact
- Include at least 1 aspirational tagline and 1 action-oriented tagline
- Maximum tagline length: 10 words
- Taglines must work standalone and alongside the brand name

### 4. Tagline Quality Filters
Post-generation quality checks:
- Reject taglines > 10 words
- Reject taglines that duplicate competitor taglines (from SKL-NTA-03)
- Reject taglines contradicting core values (from SKL-NTA-04)
- Flag taglines with potential double meanings or cross-language issues

### 5. Name-Tagline Pairing Evaluation
For each name-tagline combination:
- **Phonetic Harmony** (0-100): Do the name and tagline sound good together?
- **Semantic Reinforcement** (0-100): Does the tagline amplify the name's meaning?
- **Brevity Score** (0-100): Combined name + tagline length (shorter = higher)
- Compute a pairing score as the average of these three

## Output Schema
Write to `node_outputs.nta_taglines` with keys:
- `name_tagline_pairs`: list of `{name, taglines: [{tagline, type, character_count, rationale, emotional_impact, pairing_score: int}]}`
- `best_pairings`: list of `{name, tagline, pairing_score, rationale}` (top pairing per name)
- `quality_rejections`: list of `{tagline, rejection_reason}`
- `generation_metadata`: `{model: str, temperature: float, names_processed: int, taglines_generated: int}`

## Integration Notes
- Downstream consumers: SKL-NTA-12 (naming brief includes best pairings), SKL-NTA-14 (escalation flags low pairing scores)
- Tagline generation only runs for recommended-tier names (top 3 from SKL-NTA-10) to conserve LLM tokens
- The prompt uses Claude Sonnet 4 via the NTA agent's configured LLM client
- Taglines are creative outputs — scoring is advisory, not a hard filter
