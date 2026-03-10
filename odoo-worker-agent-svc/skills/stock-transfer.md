---
name: stock-transfer
version: "1.0"
description: Create internal stock transfers between warehouse locations
target_personas:
  - warehouse_manager
triggers:
  - "transfer"
  - "move stock"
  - "internal transfer"
  - "warehouse transfer"
mcp_tools:
  - inventory_create_transfer
  - odoo_search
priority: 7
max_tokens: 350
---
# Stock Transfer

## Workflow
1. Identify the source and destination warehouse locations using `odoo_search` on `stock.location`
2. Select the products and quantities to transfer using `odoo_search` on `product.product`
3. Create and validate the internal transfer using `inventory_create_transfer`

## Important
- Verify that sufficient stock exists at the source location before creating the transfer
- Only allow transfers between internal locations (not supplier or customer locations)
- Confirm both source and destination with the user if there are multiple warehouses
- Report the transfer reference number and expected completion after creation
