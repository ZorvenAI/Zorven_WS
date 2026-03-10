---
name: schedule-production
version: "1.0"
description: Create and schedule manufacturing production orders
target_personas:
  - manufacturing_supervisor
triggers:
  - "production order"
  - "manufacture"
  - "schedule production"
  - "work order"
mcp_tools:
  - mrp_create_production
  - odoo_search
priority: 7
max_tokens: 400
---
# Schedule Production

## Workflow
1. Search for the product to manufacture using `odoo_search` on the `product.product` model
2. Verify that a Bill of Materials (BOM) exists for the product using `odoo_search` on `mrp.bom`
3. Create the manufacturing order with quantity and scheduled date using `mrp_create_production`
4. Return the MO reference number, scheduled date, and component requirements

## Important
- A valid BOM must exist before a manufacturing order can be created
- Check component availability and report any shortages
- Set the scheduled date to the user's requested date or default to the current date
- Include the list of required components and their quantities in the response
