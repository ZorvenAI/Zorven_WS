---
name: odoo-accounts-payable
version: "1.0"
description: Bill processing and vendor payment management
target_agents:
  - odoo_mcp
triggers:
  - "bill"
  - "vendor"
  - "expense"
  - "payable"
  - "reimbursement"
priority: 8
max_tokens: 400
---
# Accounts Payable Management

## Bill Entry and Processing
- Create vendor bills from purchase orders to ensure three-way matching
- Verify bill amounts against PO lines and received quantities before posting
- Use OCR digitization to auto-extract vendor, amount, and date from uploaded PDFs
- Assign the correct expense account and analytic tags on every bill line
- Post bills only after manager approval for amounts exceeding the threshold

## Vendor Payment Scheduling
- Batch vendor payments by due date to optimize cash flow
- Prioritize payments based on early payment discount opportunities
- Use SEPA or ACH payment files for bulk bank transfers
- Schedule recurring payments for fixed-cost vendors (rent, subscriptions)
- Record payment references to simplify vendor statement reconciliation

## Expense Approval Workflow
- Employees submit expenses via the Expenses module with receipt attachments
- Direct managers approve or reject expense claims within 5 business days
- Approved expenses generate vendor bills payable to the employee
- Enforce per-category spending limits and flag policy violations automatically
- Reimburse approved expenses in the next scheduled payment batch

## Three-Way Matching
- Match purchase order, goods receipt, and vendor bill before payment authorization
- Flag discrepancies in quantity (receipt vs. PO) or price (bill vs. PO)
- Allow configurable tolerance thresholds (e.g., 2% price variance)
- Route mismatched bills to purchasing for investigation and resolution
- Only release payment after all three documents are fully reconciled
