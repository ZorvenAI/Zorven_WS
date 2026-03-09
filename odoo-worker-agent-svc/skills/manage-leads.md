---
name: manage-leads
version: "1.0"
description: Create, update, and manage CRM leads and opportunities
target_personas:
  - sales_manager
triggers:
  - "lead"
  - "opportunity"
  - "prospect"
  - "crm"
  - "pipeline stage"
mcp_tools:
  - crm_create_lead
  - crm_update_stage
  - odoo_search
priority: 7
max_tokens: 400
---
# Manage Leads

## Workflow
1. Search for existing leads or opportunities using `odoo_search` on the `crm.lead` model
2. Create a new lead with contact details and expected revenue using `crm_create_lead` if needed
3. Update the pipeline stage using `crm_update_stage` if the user requests a stage change
4. Add notes or schedule follow-up activities as requested

## Important
- Distinguish between leads (unqualified) and opportunities (qualified) based on the type field
- When moving stages, validate that the transition is logical in the sales pipeline
- Include expected revenue and probability when creating or updating opportunities
- Always confirm the target lead/opportunity if multiple matches are found
