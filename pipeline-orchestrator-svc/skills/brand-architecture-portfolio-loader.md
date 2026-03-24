---
name: brand-architecture-portfolio-loader
version: "1.0"
description: Load Company model + product portfolio for architecture input — existing brands, products, tiers, relationships (maps to SKL-BAA-03)
target_agents:
  - brand_architecture
triggers:
  - "portfolio loader"
  - "product portfolio"
  - "brand portfolio"
  - "company brands"
  - "existing products"
priority: 10
max_tokens: 400
---

# Portfolio Loader

## Purpose
Extract the focal brand's existing portfolio structure from the Company model and Discovery Agent outputs. This establishes the current-state architecture baseline that the agent will evaluate and potentially restructure.

## Methodology

### 1. Company Model Extraction
- Read `input_context.company` for core brand identity:
  - `name`: Legal/trading brand name (master brand)
  - `industry`: Primary industry vertical
  - `description`: Brand description or elevator pitch
  - `website`: Official domain
  - `target_market`: Intended audience description
- Read `input_context.company_id` for tenant-specific lookups

### 2. Discovery Agent Enrichment
- Read `previous_outputs.discovery` for web-researched brand intelligence (if available):
  - Product lines and service offerings discovered
  - Sub-brands and brand extensions identified
  - Pricing tiers observed
  - Geographic brand variations
  - Brand partnerships or co-branding relationships
- Merge with Company model data, preferring Company model for factual fields

### 3. Portfolio Inventory Construction
Build a comprehensive product/brand inventory:
- **Master Brand**: The parent company brand
- **Sub-Brands**: Named extensions under the master brand
- **Product Lines**: Distinct product categories offered
- **Endorsed Brands**: Brands with visible parent endorsement
- **Independent Brands**: Brands operated without visible parent connection
- For each entry, capture:
  - `brand_name`: The name used in market
  - `relationship_to_parent`: "master" | "sub_brand" | "product_line" | "endorsed" | "independent"
  - `category`: Product/service category
  - `tier`: "premium" | "mid" | "value" | "unknown"
  - `target_segment`: Primary audience for this brand/product
  - `status`: "active" | "planned" | "legacy"

### 4. Current Architecture Classification
- Based on the portfolio inventory, classify the current architecture model (or "undefined" if no clear model exists)
- Compute a portfolio complexity score:
  - `total_brands`: Count of distinct brand names
  - `hierarchy_depth`: Maximum nesting level
  - `category_breadth`: Number of distinct product categories
  - `tier_spread`: Number of distinct pricing tiers

### 5. Portfolio Health Indicators
- **Overlap Score** (0-100): Degree to which brands/products compete with each other internally
- **Gap Score** (0-100): Degree to which obvious category/tier gaps exist
- **Coherence Score** (0-100): How well the current portfolio tells a unified brand story

## Output Schema
Write to `node_outputs.baa_portfolio` with keys:
- `master_brand`: `{name, industry, description, category}`
- `portfolio_items`: list of `{brand_name, relationship_to_parent, category, tier, target_segment, status}`
- `current_architecture_model`: str or "undefined"
- `portfolio_complexity`: `{total_brands: int, hierarchy_depth: int, category_breadth: int, tier_spread: int}`
- `portfolio_health`: `{overlap_score: int, gap_score: int, coherence_score: int}`
- `data_sources`: list of `{source: "company_model"|"discovery", fields_contributed: []}`
- `data_quality`: `{discovery_available: bool, products_identified: int, classification_confidence: float}`

## Integration Notes
- This is typically the first BAA skill to execute; all other BAA skills reference the portfolio baseline
- Downstream consumers: SKL-BAA-06 (model recommender evaluates operational efficiency against current portfolio), SKL-BAA-07 (hierarchy builder uses portfolio items as input nodes), SKL-BAA-08 (naming designer evaluates current naming patterns)
