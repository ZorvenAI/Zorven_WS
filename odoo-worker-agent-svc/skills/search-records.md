---
name: search-records
version: "1.0"
description: Search and retrieve records from any Odoo model
target_personas:
  - general_assistant
triggers:
  - "search"
  - "find"
  - "look up"
  - "show me"
  - "list"
  - "get records"
mcp_tools:
  - odoo_search
  - odoo_read
  - odoo_fields_get
priority: 5
max_tokens: 400
---
# Search Records

## Workflow
1. Determine the appropriate Odoo model to search based on the user's request
2. Build the domain filter from the user's criteria using proper Odoo domain syntax
3. Execute the search using `odoo_search` with the constructed domain and relevant fields
4. Present the results in a clear, readable format with key fields highlighted

## Important
- Use `odoo_fields_get` to discover available fields if the model structure is unclear
- Limit results to a reasonable number (default 20) and inform the user if more exist
- Use `odoo_read` for detailed record information when the user asks about a specific record
- Format dates, monetary values, and many2one fields in a human-readable way
