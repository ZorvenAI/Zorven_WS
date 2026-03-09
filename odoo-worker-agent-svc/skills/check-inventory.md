---
name: check-inventory
version: "1.0"
description: Check current stock levels and product availability
target_personas:
  - warehouse_manager
triggers:
  - "check inventory"
  - "stock level"
  - "how many"
  - "quantity"
  - "available"
mcp_tools:
  - inventory_check_stock
  - odoo_search
priority: 7
max_tokens: 350
---
# Check Inventory

## Workflow
1. Search for the product by name or SKU using `odoo_search` on the `product.product` model
2. Check current stock levels for the matched product using `inventory_check_stock`
3. Report the available quantity broken down by warehouse location

## Important
- Distinguish between on-hand quantity, forecasted quantity, and reserved quantity
- If multiple products match the search, list them and ask the user to clarify
- Include the warehouse or location name in the response for multi-warehouse setups
- Report units of measure accurately as configured on the product
