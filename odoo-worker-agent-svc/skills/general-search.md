---
name: general-search
version: "1.0"
description: General-purpose natural language search across all Odoo models
target_personas:
  - general_assistant
triggers:
  - "what is"
  - "how many"
  - "show"
  - "display"
  - "count"
  - "read"
mcp_tools:
  - odoo_search
  - odoo_read
  - odoo_fields_get
priority: 3
max_tokens: 400
---
# General Search

## Workflow
1. Parse the natural language query to determine the target Odoo model and search criteria
2. Use `odoo_fields_get` to discover available fields on the model if needed
3. Build the appropriate domain filter and execute the search using `odoo_search`
4. Format and present the results clearly with relevant fields and record counts

## Important
- This is a fallback skill with low priority; prefer domain-specific skills when available
- Map common terms to Odoo models (e.g., "customers" to res.partner, "invoices" to account.move)
- Limit results to 20 records by default and inform the user of the total count
- Use `odoo_read` to fetch detailed information when the user asks about a specific record
