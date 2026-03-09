---
name: manage-contracts
version: "1.0"
description: Create and manage employee employment contracts
target_personas:
  - hr_manager
triggers:
  - "contract"
  - "employment contract"
  - "salary"
  - "wage"
  - "compensation"
mcp_tools:
  - hr_create_contract
  - odoo_search
priority: 6
max_tokens: 400
---
# Manage Contracts

## Workflow
1. Find the employee by name using `odoo_search` on the `hr.employee` model
2. Create or update the employment contract with salary details using `hr_create_contract`
3. Set the contract start date, end date (if fixed-term), and contract type
4. Return the contract reference and summary of terms

## Important
- Check for existing active contracts on the employee to avoid overlapping contracts
- Required fields include employee, wage, contract start date, and contract type
- Do not expose full salary details in responses unless the requesting user has HR manager access
- Support different wage structures (monthly, hourly) based on the contract type
