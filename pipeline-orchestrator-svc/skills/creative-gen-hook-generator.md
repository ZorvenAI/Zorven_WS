---
name: creative-gen-hook-generator
version: "1.0"
description: Generate 3-5 hook variants per audience x funnel using funnel-appropriate techniques (TOFU curiosity, MOFU pain-point, BOFU urgency/proof) (maps to SKL-CGA-07)
target_agents:
  - creative_generation
triggers:
  - "ad hooks"
  - "hook variants"
  - "headline generation"
  - "attention hooks"
priority: 10
max_tokens: 800
---

# Hook Generator

## Purpose
Generate 3-5 compelling hook variants for each audience x funnel combination. Hooks are the first line of ad copy that must stop the scroll. Each funnel stage uses distinct psychological techniques: TOFU leverages curiosity and emotion, MOFU addresses pain points and consideration factors, BOFU drives urgency and social proof.

## Methodology

### 1. Load Inputs
From upstream skill outputs:
- `node_outputs.cga_audience_profiles` -- creative profiles per audience x funnel
- `node_outputs.cga_context` -- brand identity, customer language, competitor patterns
- `node_outputs.cga_learnings` -- winning/losing hook patterns (if available)

### 2. Apply Funnel-Stage Hook Techniques

**TOFU (Awareness) Hooks** -- Stop the scroll:
- Curiosity gap: "The [industry] secret that [outcome]..."
- Emotional trigger: Lead with aspiration, fear of missing out, or surprise
- Pattern interrupt: Unexpected statement or contrarian take
- Question hook: Rhetorical question targeting audience pain/desire
- Statistical shock: Compelling data point from market research

**MOFU (Consideration) Hooks** -- Deepen engagement:
- Pain-point agitation: Name the specific problem the audience faces
- Comparison frame: "Still doing [old way]? There's a better approach"
- Social proof lead: "Join [number] [audience peers] who..."
- Benefit stack: Lead with the top 2-3 benefits
- Story hook: Mini-narrative opening that draws the reader in

**BOFU (Conversion) Hooks** -- Drive action:
- Urgency trigger: Time-limited offer, scarcity signal
- Proof statement: Testimonial quote, case study result, metric
- Direct value prop: Clear, specific offer with tangible outcome
- Risk reversal: "Try [product] risk-free" or guarantee lead
- Final objection killer: Address the #1 hesitation directly

### 3. Brand Voice Alignment
For each generated hook:
- Apply brand voice matrix (formal/casual, witty/serious, bold/understated)
- Verify alignment with brand personality archetype
- Incorporate customer language patterns from VoC data
- Ensure consistency with brand tagline tone

### 4. Competitive Differentiation
- Cross-reference hooks against competitor ad copy patterns
- Avoid hooks that mirror competitor messaging too closely
- Emphasize brand differentiators from positioning data

### 5. Quality Scoring
Rate each hook on:
- **Scroll-stop potential** (1-5): Would this make someone pause?
- **Relevance** (1-5): Does it speak to this specific audience?
- **Brand alignment** (1-5): Does it sound like the brand?
- **Uniqueness** (1-5): Is it differentiated from competitors?
- Composite score = weighted average (scroll-stop 0.4, relevance 0.3, brand 0.2, uniqueness 0.1)

## Output Schema
Write to `node_outputs.cga_hooks` with keys:
- `hooks`: list of hook sets, each containing:
  - `audience_name`: string
  - `funnel_stage`: string
  - `profile_id`: string
  - `variants`: list of hook objects with `hook_text`, `technique`, `quality_score`, `scores_breakdown`
- `total_hooks`: int
- `avg_quality_score`: float

## Integration Notes
- Hooks are paired with primary copy in SKL-CGA-08 and CTAs in SKL-CGA-09
- Hook length should stay under 125 characters for optimal Meta ad display
- Hooks undergo compliance screening in SKL-CGA-10 before final assembly
- Quality scores influence variant ranking in SKL-CGA-11 (assembler)
