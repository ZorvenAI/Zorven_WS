---
name: create-purchase-order
version: "1.0"
description: Create a new purchase order or request for quotation to a vendor
target_personas:
  - procurement_officer
triggers:
  - "purchase order"
  - "buy"
  - "procure"
  - "vendor order"
  - "rfq"
mcp_tools:
  - inventory_create_purchase_order
  - odoo_search
priority: 7
max_tokens: 400
---
# Create Purchase Order

## Workflow
1. Search for the vendor by name using `odoo_search` on the `res.partner` model with supplier filter
2. Search for the products to purchase using `odoo_search` on the `product.product` model
3. Create the purchase order with the vendor ID and order lines (product, quantity, unit price) using `inventory_create_purchase_order`
4. Return the PO reference number and status

## Important
- Filter vendor search to only include suppliers (supplier_rank > 0)
- Use the product's default vendor price if no price is specified by the user
- Set the expected delivery date if provided
- Do not confirm the PO automatically unless the user explicitly requests it
