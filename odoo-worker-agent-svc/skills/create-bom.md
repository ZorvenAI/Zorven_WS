---
name: create-bom
version: "1.0"
description: Create a Bill of Materials with components for manufacturing
target_personas:
  - manufacturing_supervisor
triggers:
  - "bill of materials"
  - "bom"
  - "recipe"
  - "components"
mcp_tools:
  - mrp_create_bom
  - odoo_search
priority: 7
max_tokens: 400
---
# Create Bill of Materials

## Workflow
1. Search for the finished product using `odoo_search` on the `product.product` model
2. Define the component list with quantities by searching each component product
3. Create the BOM using `mrp_create_bom` with the product and component lines
4. Set the routing or operation steps if applicable

## Important
- Verify that all component products exist in the system before creating the BOM
- Set the BOM type (manufacture or kit) based on the user's intent
- Include the unit of measure for each component line
- Check for existing BOMs on the same product to avoid unintended duplicates
