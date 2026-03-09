---
name: executive-dashboard
version: "1.0"
description: Compile executive KPIs and performance metrics across departments
target_personas:
  - executive
triggers:
  - "dashboard"
  - "kpi"
  - "overview"
  - "metrics"
  - "performance"
  - "summary"
mcp_tools:
  - odoo_search
  - accounting_get_report
  - odoo_read
priority: 8
max_tokens: 500
---
# Executive Dashboard

## Workflow
1. Gather key financial metrics (revenue, expenses, profit) using `accounting_get_report`
2. Collect operational data (open orders, inventory levels, active projects) using `odoo_search`
3. Compile HR metrics (headcount, open positions, leave summary) using `odoo_search` and `odoo_read`
4. Present a consolidated executive summary with KPIs and notable trends

## Important
- Default to current month/quarter metrics unless a specific period is requested
- Present data in a structured format with clear section headings
- Highlight metrics that are significantly above or below expected thresholds
- Include period-over-period comparisons when historical data is available
