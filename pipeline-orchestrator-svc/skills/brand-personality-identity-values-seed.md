---
name: brand-personality-identity-values-seed
version: "1.0"
description: Map Company.brand_voice and Company.values to initial Aaker 5D seed weights and extract founder intent for personality grounding (maps to SKL-BPV-03)
target_agents:
  - brand_personality
triggers:
  - "identity seed"
  - "values seed"
  - "brand voice seed"
  - "aaker seed"
  - "founder intent"
priority: 10
max_tokens: 500
---

# Identity & Values Seed Loader

## Purpose
Extract the brand's self-declared identity from the Company model — specifically `brand_voice`, `values`, `description`, and `target_market` — and translate these into initial Aaker 5-dimension seed weights. This provides the founder-intent anchor that prevents the personality profile from drifting away from the brand's core identity during data-driven analysis.

## Methodology

### 1. Company Model Extraction
- Read `input_context.company` for identity signals:
  - `brand_voice`: Free-text description of desired brand voice/tone
  - `values`: Stated brand values (comma-separated or list)
  - `description`: Brand elevator pitch
  - `target_market`: Intended audience description
  - `industry`: Category vertical
- Read `previous_outputs.discovery` for enriched brand positioning data (if available)

### 2. Brand Voice Parsing
Analyze `brand_voice` text for personality indicators:
- Tokenize voice descriptors (e.g., "professional yet approachable" -> ["professional", "approachable"])
- Map each descriptor to Aaker dimensions using a keyword-dimension lookup:

| Keywords | Aaker Dimension |
|---|---|
| honest, genuine, authentic, transparent, wholesome, cheerful | Sincerity |
| exciting, daring, spirited, imaginative, innovative, bold | Excitement |
| reliable, competent, intelligent, successful, professional | Competence |
| glamorous, charming, elegant, sophisticated, premium | Sophistication |
| tough, rugged, outdoorsy, strong, resilient, durable | Ruggedness |

- Compute initial seed weight per dimension (0.0-1.0) based on descriptor frequency and strength

### 3. Values-to-Trait Mapping
Map declared brand values to personality traits:
- Core values (e.g., "integrity") -> Sincerity traits
- Innovation values (e.g., "disruption") -> Excitement traits
- Excellence values (e.g., "quality") -> Competence traits
- Aesthetic values (e.g., "elegance") -> Sophistication traits
- Resilience values (e.g., "endurance") -> Ruggedness traits
- Values that span multiple dimensions receive split weights

### 4. Industry Baseline
Apply industry-typical personality baselines:
- Technology: Competence (high), Excitement (moderate)
- Luxury: Sophistication (high), Competence (moderate)
- Outdoor/Sports: Ruggedness (high), Excitement (moderate)
- Healthcare: Sincerity (high), Competence (high)
- FMCG: Sincerity (moderate), Excitement (moderate)
- Use industry baseline as a floor, not a ceiling — founder intent always takes priority

### 5. Seed Weight Normalization
- Combine brand_voice weights, values weights, and industry baseline
- Normalize so all 5 dimensions sum to 1.0
- Identify the dominant seed dimension (highest weight)
- Flag if any dimension has zero representation (potential blind spot)

## Output Schema
Write to `node_outputs.bpv_identity_seed` with keys:
- `seed_weights`: `{sincerity: float, excitement: float, competence: float, sophistication: float, ruggedness: float}`
- `dominant_seed_dimension`: str
- `voice_descriptors`: list of `{descriptor, mapped_dimension, confidence}`
- `values_mapping`: list of `{value, mapped_dimension, weight}`
- `industry_baseline`: `{sincerity: float, excitement: float, competence: float, sophistication: float, ruggedness: float}`
- `blind_spots`: list of str (dimensions with zero or near-zero representation)
- `data_quality`: `{brand_voice_present: bool, values_present: bool, discovery_available: bool, descriptors_parsed: int}`

## Integration Notes
- Downstream consumers: SKL-BPV-05 (Aaker profiler uses seed weights as the founder-intent anchor with 30% weight in the final profile)
- Seed weights are not the final profile — they represent brand intent, which is then adjusted by audience psychology (SKL-BPV-01) and perception data (SKL-BPV-02)
- If `brand_voice` is empty, fall back to `description` text analysis with reduced confidence
