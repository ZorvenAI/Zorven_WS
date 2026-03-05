---
name: odoo-payroll-admin
version: "1.0"
description: Payroll processing and salary structure management
target_agents:
  - odoo_mcp
triggers:
  - "payroll"
  - "salary"
  - "payslip"
  - "wage"
  - "compensation"
priority: 7
max_tokens: 400
---
# Payroll Administration

## Salary Structure and Rules
- Define salary structures as ordered sets of salary rules (e.g., Basic, HRA, Tax, Net)
- Each rule computes a line on the payslip using Python expressions or fixed amounts
- Categorize rules into groups: Gross, Deduction, Employer Contribution, Net
- Support multiple structures for different employee categories (staff, management, hourly)
- Test rule formulas with sample data before deploying to production payslips

## Payslip Generation
- Generate payslips individually or in bulk via payslip batches for the pay period
- Verify worked days and input entries (overtime, bonuses, deductions) before computation
- Run the "Compute Sheet" action to calculate all salary rule lines
- Review computed payslips for anomalies: zero net, negative values, or large variances
- Confirm payslips to post the corresponding journal entries to accounting

## Statutory Deductions
- Configure statutory deduction rules per jurisdiction (income tax, social security, health insurance)
- Update tax brackets and contribution rates annually at legislative changes
- Track employer-side contributions separately from employee deductions
- Generate statutory declaration reports for tax filing and social security submissions
- Maintain audit trails for all deduction calculations with rule version history

## Batch Processing
- Group payslips into monthly batches for streamlined processing
- Validate the entire batch before confirming to catch errors early
- Generate bank payment files (SEPA, ACH) from confirmed payslip batches
- Post batch journal entries in a single accounting move for clean reconciliation
- Archive completed batches and retain payslip PDFs for employee self-service access
