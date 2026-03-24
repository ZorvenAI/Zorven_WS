---
name: brand-architecture-naming-designer
version: "1.0"
description: Design naming patterns and conventions for the brand hierarchy, produce consistency score (0-100) and naming guidelines (maps to SKL-BAA-08)
target_agents:
  - brand_architecture
triggers:
  - "naming design"
  - "naming conventions"
  - "brand naming"
  - "naming patterns"
  - "nomenclature"
priority: 9
max_tokens: 500
---

# Brand Naming Designer

## Purpose
Design a cohesive naming system for the recommended brand architecture hierarchy. Naming is the most visible expression of architecture — it must signal relationships between brands, communicate tier positioning, and be operationally sustainable as the portfolio grows.

## Methodology

### 1. Input Collection
- Read SKL-BAA-06 `baa_model_recommendation` for the recommended architecture model
- Read SKL-BAA-07 `baa_hierarchy` for the brand hierarchy tree
- Read SKL-BAA-03 `baa_portfolio` for existing brand names and current naming patterns
- Read SKL-BAA-04 `baa_positioning_context` for positioning constraints on naming
- Read SKL-BAA-05 `baa_rag_context` for prior naming guidelines (if available)

### 2. Current Naming Pattern Analysis
Analyze existing brand names in the portfolio for patterns:
- **Prefix patterns**: Does the parent brand appear as a prefix? (e.g., "Acme Pro", "Acme Lite")
- **Suffix patterns**: Does a descriptor follow the brand? (e.g., "Pro", "Plus", "Studio")
- **Independent patterns**: Are names completely unrelated to the parent? (e.g., "Tide" under P&G)
- **Endorsed patterns**: Is the parent appended? (e.g., "Courtyard by Marriott")
- **Alphanumeric patterns**: Are names using codes or numbers? (e.g., "BMW 3 Series")
- Compute current naming consistency: percentage of names following the dominant pattern

### 3. Naming Convention Rules by Architecture Model

**Branded House**:
- Rule: `{Master Brand} + {Descriptor/Modifier}`
- Examples: "Google Maps", "Google Drive", "Google Photos"
- Modifier vocabulary: functional descriptors, tier indicators, audience labels
- Prohibited: Names with no visible connection to master brand

**House of Brands**:
- Rule: Each brand has a unique, standalone name
- Corporate brand visible only at investor/legal level
- Naming evaluation: distinctiveness, memorability, category fit
- Prohibited: Parent brand name in consumer-facing brand names

**Endorsed**:
- Rule: `{Sub-Brand} + "by" + {Master Brand}`
- Variation: `{Master Brand} + "presents" + {Sub-Brand}`
- Endorsement weight: strong ("by"), moderate ("from"), light (logo only)
- Prohibited: Mixing endorsement styles within the same tier

**Hybrid**:
- Rule: Different naming conventions per portfolio segment
- Must define explicit rules for which segment uses which convention
- Transition naming for brands moving between categories

**Sub-Brand**:
- Rule: `{Master Brand} + {Sub-Brand Name}`
- Sub-brand names should be evocative, not purely descriptive
- Examples: "Apple iPhone", "Apple MacBook", "Apple AirPods"
- Prohibited: Sub-brand names that overshadow the master brand

### 4. Naming Recommendations
For each node in the hierarchy (from SKL-BAA-07):
- If `status: "existing"`: Evaluate current name against conventions, recommend rename if inconsistent
- If `status: "recommended_new"`: Generate 2-3 name candidates following the convention
- If `status: "recommended_restructure"`: Propose a transition name if renaming is needed
- For each recommendation, provide:
  - Recommended name or "retain current"
  - Convention rule applied
  - Rationale for the choice

### 5. Consistency Scoring (0-100)
Compute the overall naming consistency score:
- **Pattern Adherence** (0-40): % of names following the recommended convention
- **Relationship Clarity** (0-30): How clearly names signal brand relationships
- **Distinctiveness** (0-15): Names are unique and not confusable with each other
- **Scalability** (0-15): Naming system can accommodate future additions without breaking
- Total = Pattern Adherence + Relationship Clarity + Distinctiveness + Scalability

## Output Schema
Write to `node_outputs.baa_naming` with keys:
- `naming_convention`: `{model, rule_description, examples: [], prohibited: []}`
- `node_naming`: list of `{node_id, current_name, recommended_name, convention_rule, rationale, action: "retain"|"rename"|"new"}`
- `consistency_score`: int (0-100)
- `consistency_breakdown`: `{pattern_adherence: int, relationship_clarity: int, distinctiveness: int, scalability: int}`
- `naming_guidelines`: list of `{guideline, category: "mandatory"|"recommended"|"prohibited", rationale}`
- `name_candidates`: list of `{node_id, candidates: [{name, rationale, score}]}` (for new/restructured nodes)

## Integration Notes
- Downstream consumers: SKL-BAA-10 (strategy synthesis includes naming guidelines in implementation section)
- Naming guidelines become hard constraints for future brand creation in the platform
- `consistency_score` < 40 triggers an advisory escalation in SKL-BAA-12
- SKL-BAA-11 (persister) archives naming guidelines for future RAG retrieval
