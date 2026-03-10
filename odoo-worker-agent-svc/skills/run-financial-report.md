---
name: run-financial-report
version: "1.0"
description: Generate financial reports such as balance sheet, P&L, or cash flow
target_personas:
  - financial_controller
  - executive
triggers:
  - "financial report"
  - "balance sheet"
  - "profit and loss"
  - "income statement"
  - "cash flow"
mcp_tools:
  - accounting_get_report
  - odoo_search
priority: 8
max_tokens: 400
---
# Run Financial Report

## Workflow
1. Determine the report type requested (balance sheet, profit and loss, cash flow statement, or general ledger)
2. Set the date range based on user input or default to the current fiscal period
3. Run the report using `accounting_get_report` with the appropriate parameters
4. Format and present the results with clear section headings and totals

## Important
- Default to the current fiscal year if no date range is specified
- Support comparison periods (e.g., current vs. previous year) if requested
- Present monetary values with proper currency formatting
- Summarize key figures at the top before showing the detailed breakdown
