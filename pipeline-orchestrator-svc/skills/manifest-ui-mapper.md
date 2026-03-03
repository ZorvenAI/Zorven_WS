---
name: manifest-ui-mapper
version: "1.0"
description: Generate UI schema from pipeline manifest for frontend chart rendering
target_agents:
  - manager
triggers:
  - "analysis"
  - "brand"
  - "valuation"
  - "equity"
  - "report"
  - "dashboard"
  - "score"
  - "research"
  - "blog"
priority: 10
max_tokens: 450
---
# ManifestUIMapper — Pipeline Result to UI Schema

## Purpose
Generate a UI configuration object from the pipeline's result_data that
tells the Next.js frontend which charts, gauges, and visualizations to
render for the completed analysis.

## UI Component Mapping

### Brand Equity / Valuation Pipeline
When result_data contains `bsi` (Brand Strength Index) or `valuation` data:
```json
{
  "ui_schema": {
    "type": "brand_equity_dashboard",
    "charts": [
      {"type": "radar_chart", "data_key": "bsi.pillars", "label": "Brand Strength Pillars"},
      {"type": "score_gauge", "data_key": "score", "max": 100, "label": "Overall BSI Score"},
      {"type": "valuation_card", "data_key": "valuation.brand_value_npv", "label": "Brand Value"}
    ]
  }
}
```

### Content Pipeline (Blog + Social)
When result_data contains `blog_content` or `adapted_posts`:
```json
{
  "ui_schema": {
    "type": "content_dashboard",
    "charts": [
      {"type": "word_count_badge", "data_key": "word_count"},
      {"type": "seo_score_card", "data_key": "seo_meta"},
      {"type": "platform_cards", "data_key": "adapted_posts"}
    ]
  }
}
```

### Research-Only Pipeline
When result_data contains only `findings` and `sources`:
```json
{
  "ui_schema": {
    "type": "research_dashboard",
    "charts": [
      {"type": "findings_list", "data_key": "findings"},
      {"type": "sources_table", "data_key": "sources"}
    ]
  }
}
```

## Schema Rules
- The `type` field determines which React component the frontend renders
- Each chart entry maps a `data_key` to a path in the result_data JSON
- Include `label` for human-readable chart titles
- Only include charts for data that actually exists in the result
- Do not include chart entries for empty or null data keys

## ISO 10668 Pillar Mapping for Radar Chart
When BSI pillars are present, map to radar chart axes:
- Financial Strength → "Financial"
- Behavioral Measures / Awareness → "Awareness"
- Legal Protection → "Legal"
- Market Position → "Market"
- Brand Loyalty → "Loyalty"

## Fallback
If the pipeline result does not match any known pattern, use:
```json
{
  "ui_schema": {
    "type": "generic_result",
    "charts": [
      {"type": "findings_list", "data_key": "findings"},
      {"type": "recommendations_list", "data_key": "recommendations"}
    ]
  }
}
```
