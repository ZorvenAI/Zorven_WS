---
name: process-payment
version: "1.0"
description: Register payments against open invoices
target_personas:
  - accountant
triggers:
  - "payment"
  - "register payment"
  - "pay invoice"
  - "receive payment"
mcp_tools:
  - accounting_register_payment
  - odoo_search
priority: 7
max_tokens: 350
---
# Process Payment

## Workflow
1. Find the open invoice by number or customer name using `odoo_search` on `account.move`
2. Register the payment with amount, payment method, and date using `accounting_register_payment`
3. Reconcile the payment with the invoice and confirm the updated balance

## Important
- Verify the payment amount does not exceed the invoice balance
- Support partial payments and clearly report the remaining balance
- Confirm the payment journal (bank, cash) before processing
- Display the invoice status after payment (paid, partial, or still open)
