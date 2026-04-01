---
name: creative-gen-copy-compliance
version: "1.0"
description: Screen all generated copy (hooks, primary text, CTAs) against Meta Advertising Standards and flag policy violations before assembly (maps to SKL-CGA-10)
target_agents:
  - creative_generation
triggers:
  - "copy compliance"
  - "ad policy check"
  - "Meta advertising standards"
  - "compliance screening"
priority: 10
max_tokens: 800
---

# Copy Compliance Screener

## Purpose
Screen all generated copy elements (hooks, primary copy, CTA text) against Meta Advertising Standards policies. Flag violations, suggest compliant alternatives, and gate the pipeline to prevent non-compliant creative from reaching the final package.

## Methodology

### 1. Collect All Copy Elements
Gather from upstream outputs:
- `node_outputs.cga_hooks` -- all hook variants
- `node_outputs.cga_primary_copy` -- all primary copy variants (short, medium, long)
- `node_outputs.cga_ctas` -- all CTA text variants

### 2. Meta Advertising Standards Checks

**Prohibited Content Screening**:
- Discriminatory practices (race, ethnicity, religion, gender, disability)
- Deceptive or misleading claims (fake urgency, false scarcity)
- Adult content or sexual suggestiveness
- Sensationalist language or shock tactics
- Profanity or offensive language
- Surveillance or data collection implications

**Restricted Category Compliance**:
- **Housing**: No age, gender, ZIP code targeting language
- **Credit/Financial**: No income guarantees, no misleading APR claims
- **Employment**: No discriminatory qualification language
- **Health/Pharma**: No unapproved medical claims, no before/after implications
- **Alcohol**: Age-gating language required where applicable
- **Political**: Disclaimer requirements flagged

**Copy-Specific Rules**:
- No ALL CAPS in more than one word per sentence
- No excessive punctuation (!!!, ???)
- No misleading buttons or fake interactive elements in text
- No personal attributes assumptions ("Are you overweight?")
- Grammar and spelling check (broken copy reduces ad approval rates)

### 3. Severity Classification
Classify each finding:
- **BLOCK**: Guaranteed policy rejection, must be fixed (e.g., discriminatory language)
- **WARN**: Likely to trigger review, recommend revision (e.g., aggressive urgency)
- **INFO**: Best practice suggestion, not a policy violation (e.g., excessive capitalization)

### 4. Generate Compliant Alternatives
For each BLOCK or WARN finding:
- Suggest 1-2 compliant rewrites that preserve the original intent
- Maintain brand voice in rewrites
- Flag rewrites as machine-suggested for human review

### 5. Compliance Scoring
Score each copy element:
- **Pass**: No BLOCK or WARN findings
- **Conditional**: WARN findings only, can proceed with caution
- **Fail**: BLOCK findings, must be revised before assembly

### 6. Aggregate Compliance Report
Produce a summary for the full creative set:
- Total elements screened
- Pass/conditional/fail counts
- Most common violation types
- Industry-specific compliance notes

## Output Schema
Write to `node_outputs.cga_compliance` with keys:
- `screening_results`: list of result objects, each containing:
  - `element_type`: "hook" | "primary_copy" | "cta"
  - `element_id`: string (variant ID or CTA ID)
  - `original_text`: string
  - `status`: "pass" | "conditional" | "fail"
  - `findings`: list of `{rule, severity, description, suggested_fix}`
- `summary`: dict with `total_screened`, `passed`, `conditional`, `failed`
- `compliant_alternatives`: list of `{element_id, original, rewrite, rule_addressed}`
- `industry_notes`: list[str]
- `overall_compliance_rate`: float (0-1)

## Integration Notes
- This skill gates SKL-CGA-11 (assembler); failed elements are excluded unless fixed
- Compliance alternatives can be auto-substituted or flagged for human review
- Industry detection uses the brand's industry from company profile
- Special Ad Category from CAA blueprint triggers stricter screening rules
- Re-run compliance if copy is manually edited post-generation
