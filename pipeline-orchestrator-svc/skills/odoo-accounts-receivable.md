---
name: odoo-accounts-receivable
version: "1.0"
description: Invoice management and payment collection
target_agents:
  - odoo_mcp
triggers:
  - "invoice"
  - "payment"
  - "receivable"
  - "collection"
  - "due"
priority: 8
max_tokens: 400
---
# Accounts Receivable Management

## Invoice Creation Workflow
- Generate invoices directly from confirmed sales orders for traceability
- Validate tax computation and fiscal position before posting
- Use the "Post and Send" action to confirm and email invoices in one step
- Apply the correct journal and account mapping based on product category
- Number invoices sequentially per journal with no gaps in production sequences

## Payment Matching and Reconciliation
- Register payments against specific invoices using the "Register Payment" wizard
- Enable batch payments for processing multiple customer payments simultaneously
- Use bank statement reconciliation to auto-match payments by reference and amount
- Handle partial payments by keeping the invoice open with the residual amount
- Write off small differences (under threshold) during reconciliation

## Aging Analysis
- Run the Aged Receivable report weekly to monitor overdue balances
- Standard aging buckets: Current, 1-30 days, 31-60 days, 61-90 days, 90+ days
- Flag accounts exceeding their credit limit for sales hold review
- Export aging data for executive review with partner and salesperson grouping

## Follow-Up Procedures
- Configure automated follow-up levels with escalating urgency
- Level 1 (7 days overdue): polite email reminder
- Level 2 (30 days overdue): formal letter with statement attached
- Level 3 (60 days overdue): phone call action assigned to collections team
- Level 4 (90+ days overdue): escalate to legal or write-off review
