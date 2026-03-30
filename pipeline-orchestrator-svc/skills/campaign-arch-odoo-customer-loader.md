---
name: campaign-arch-odoo-customer-loader
version: "1.0"
description: Load customer data from Odoo CRM for custom and lookalike audience building; optional skill that gracefully degrades when Odoo is unavailable (maps to SKL-CAA-04)
target_agents:
  - campaign_architecture
triggers:
  - "odoo customers"
  - "crm data"
  - "customer audience"
  - "custom audience data"
priority: 10
max_tokens: 400
---

# Odoo Customer Loader

## Purpose
Extract customer data from Odoo CRM to enable custom audience and lookalike audience creation in Meta Ads. This is an optional enrichment step — the campaign architecture proceeds without it when Odoo is unavailable.

## Methodology

### 1. Odoo Availability Check
Verify Odoo MCP Server connectivity:
- Endpoint: `GET {ODOO_MCP_SERVER_URL}/health`
- Timeout: 5 seconds
- If unavailable, return empty result with `odoo_available: false`

### 2. Customer Data Extraction
Via Odoo MCP Server tools:
- `search_read_contacts`: Retrieve customer records with email, phone, purchase history
- `search_read_sale_orders`: Retrieve order data for LTV segmentation
- Filters: active customers only, created within last 24 months

### 3. Customer Segmentation
Segment customers for audience building:
- **High-Value**: Top 20% by lifetime value (best for lookalike seed)
- **Recent Purchasers**: Last 90 days (best for retention campaigns)
- **Engaged Non-Buyers**: Contacts with interactions but no purchases (best for MOFU)
- **Lapsed**: No activity in 180+ days (best for win-back campaigns)

### 4. Audience Readiness Assessment
Evaluate audience viability:
- Minimum 100 customers required for Meta custom audience upload
- Minimum 1,000 customers recommended for effective lookalike audiences
- Email match rate typically 30-50% on Meta (factor into size estimates)

### 5. Data Sanitization
Before including in output:
- Strip PII (no raw emails/phones in campaign blueprint)
- Aggregate to segment-level statistics only
- Include segment sizes and metadata, not individual records

## Output Schema
Write to `node_outputs.caa_odoo_customers` with keys:
- `odoo_available`: boolean
- `total_customers`: int
- `segments`: list of `{segment_name, count, avg_ltv, recency_days}`
- `custom_audience_viable`: boolean (true if >= 100 customers)
- `lookalike_viable`: boolean (true if >= 1,000 customers)
- `recommended_seed_segment`: string | null (segment name for lookalike seed)
- `estimated_match_rate`: float (0-1)

## Integration Notes
- Consumed by SKL-CAA-07 (audience targeting builder) for custom/lookalike audience specs
- This skill is OPTIONAL — all downstream skills handle `odoo_available: false` gracefully
- Customer data is never persisted in the campaign blueprint — only segment metadata
- Requires X-Tenant-ID header for Odoo MCP Server routing
