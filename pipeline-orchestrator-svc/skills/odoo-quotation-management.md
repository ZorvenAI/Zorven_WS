---
name: odoo-quotation-management
version: "1.0"
description: Quotation and sales order lifecycle management
target_agents:
  - odoo_mcp
triggers:
  - "quotation"
  - "quote"
  - "order"
  - "sales order"
priority: 8
max_tokens: 400
---
# Quotation and Sales Order Management

## Quote-to-Order Workflow
- Create quotations from CRM opportunities to maintain traceability
- Use quotation templates for recurring product bundles and standard offerings
- Set an expiration date on every quotation (default: 15 days)
- Send quotations via email with the online signature portal enabled
- Confirm the quotation to convert it into a sales order automatically

## Discount Approval Process
- Sales reps may apply discounts up to 10% without approval
- Discounts between 10-20% require sales manager confirmation
- Discounts above 20% require director-level approval via the approval workflow
- Log all discount reasons in the internal notes for audit purposes

## Order Confirmation Rules
- Verify stock availability before confirming delivery-dependent orders
- Validate customer credit limit against the outstanding receivable balance
- Automatically create delivery orders and invoices upon confirmation
- Lock confirmed sales orders to prevent unauthorized line item changes

## Payment Terms Configuration
- Define standard payment terms: Immediate, Net 15, Net 30, Net 60
- Apply early payment discounts (e.g., 2/10 Net 30) via payment term lines
- Set default payment terms per customer on the partner record
- Use fiscal position mapping to adjust terms for international customers
