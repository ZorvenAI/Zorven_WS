---
name: odoo-multi-currency
version: "1.0"
description: Multi-currency transaction and exchange rate management
target_agents:
  - odoo_worker
triggers:
  - "currency"
  - "exchange rate"
  - "foreign"
  - "FX"
priority: 6
max_tokens: 400
---
# Multi-Currency Management

## Exchange Rate Configuration
- Activate required currencies under Accounting > Configuration > Currencies
- Set the company currency as the base currency for all accounting entries
- Configure automatic exchange rate updates from ECB, Federal Reserve, or custom provider
- Schedule rate updates daily to ensure accurate transaction conversion
- Manually override rates for specific dates when contractual rates apply

## Transaction Processing
- Select the transaction currency on invoices, bills, and payments
- Odoo records both the foreign currency amount and the company currency equivalent
- Use the rate at invoice date for revenue recognition and cost recording
- Apply the rate at payment date when registering customer or vendor payments
- The exchange difference journal entry is created automatically on reconciliation

## Unrealized Gains and Losses
- Run the currency revaluation wizard at each reporting period close
- Revaluation adjusts open receivable and payable balances to the closing rate
- Post unrealized gains to the "Unrealized Exchange Gain" account (configurable)
- Post unrealized losses to the "Unrealized Exchange Loss" account (configurable)
- Reverse revaluation entries at the start of the next period automatically

## Currency Revaluation Best Practices
- Always revalue before generating financial statements
- Document the exchange rate source used for each revaluation run
- Reconcile the exchange difference account monthly to catch anomalies
- Report realized vs. unrealized FX impact separately for management review
- Monitor high-exposure currency pairs and consider hedging for material balances
