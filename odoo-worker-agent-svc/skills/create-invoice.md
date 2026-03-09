---
name: create-invoice
version: "1.0"
description: Create a new customer or vendor invoice
target_personas:
  - accountant
triggers:
  - "create invoice"
  - "new invoice"
  - "bill customer"
  - "invoice"
mcp_tools:
  - accounting_create_invoice
  - odoo_search
priority: 8
max_tokens: 400
---
# Create Invoice

## Workflow
1. Search for the customer or vendor by name using `odoo_search` on the `res.partner` model
2. Look up the products or services to be invoiced using `odoo_search` on the `product.product` model
3. Create the invoice with line items including product, quantity, price, and tax using `accounting_create_invoice`
4. Validate the invoice and return the invoice number and total amount

## Important
- Determine whether this is a customer invoice (out_invoice) or vendor bill (in_invoice) based on context
- Ensure tax accounts and fiscal positions are applied correctly
- Do not auto-post the invoice unless the user explicitly requests it
- Include payment terms if specified by the user
