---
name: odoo-financial-reporting
version: "1.0"
description: Financial statement generation and analysis
target_agents:
  - odoo_worker
triggers:
  - "balance sheet"
  - "P&L"
  - "profit"
  - "financial report"
  - "trial balance"
priority: 7
max_tokens: 400
---
# Financial Reporting

## Standard Report Types
- **Balance Sheet**: Assets, liabilities, and equity at a point in time
- **Profit and Loss**: Revenue and expenses over a reporting period
- **Trial Balance**: Debit and credit totals for all accounts as a verification tool
- **General Ledger**: Detailed transaction-level view per account
- **Cash Flow Statement**: Operating, investing, and financing cash movements
- **Aged Partner Balance**: Receivable and payable aging by partner

## Period Closing Process
- Reconcile all bank statements for the period before closing
- Review and post all draft journal entries (invoices, bills, manual entries)
- Run the unrealized currency gains/losses wizard for multi-currency accounts
- Verify inter-company balances and eliminate transactions for consolidated reports
- Lock the fiscal period to prevent backdated entries after close
- Use the "Lock Date for Non-Advisers" to restrict edits while allowing accountant access

## Chart of Accounts Best Practices
- Follow local GAAP or IFRS account numbering conventions
- Group accounts by type: Asset, Liability, Equity, Income, Expense
- Create sub-accounts for departmental or project-level tracking
- Avoid deleting accounts with posted entries -- mark them as deprecated instead
- Review and clean up unused accounts annually

## Analytical Accounting
- Define analytic plans for cost center, project, and department tracking
- Apply analytic distributions on journal items for multi-dimensional reporting
- Use analytic filters on P&L reports to view profitability by project or department
- Set budget lines per analytic account and compare actuals against budget
