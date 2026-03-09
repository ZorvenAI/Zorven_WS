---
name: create-sales-order
version: "1.0"
description: Create a new sales order or quotation for a customer
target_personas:
  - sales_manager
triggers:
  - "sales order"
  - "create order"
  - "new order"
  - "quotation"
mcp_tools:
  - odoo_search
  - sales_create_order
priority: 8
max_tokens: 400
---
# Create Sales Order

## Workflow
1. Search for the customer by name or email using `odoo_search` on the `res.partner` model
2. Search for the requested products by name or internal reference using `odoo_search` on the `product.product` model
3. Create the sales order with the resolved customer ID and order lines (product, quantity, unit price) using `sales_create_order`
4. Return the order number, total amount, and current status to the user

## Important
- Always confirm the customer identity before creating the order if multiple matches are found
- Validate that all requested products exist and are saleable before submitting the order
- Include unit of measure and any discount if specified by the user
- If the customer does not exist, inform the user rather than creating a new contact automatically
