---
name: odoo-leave-management
version: "1.0"
description: Leave requests and absence tracking
target_agents:
  - odoo_mcp
triggers:
  - "leave"
  - "time off"
  - "vacation"
  - "holiday"
  - "absence"
priority: 7
max_tokens: 400
---
# Leave and Absence Management

## Leave Types Configuration
- Define leave types: Paid Time Off, Sick Leave, Unpaid Leave, Compensatory, Parental
- Set whether each type requires allocation (limited balance) or is open (unlimited)
- Configure approval levels: no approval, manager approval, or HR approval
- Specify whether the leave type is visible to employees in the self-service portal
- Color-code leave types for easy identification on team calendars

## Allocation Rules
- Create annual allocation plans that auto-grant leave balances on a schedule
- Support accrual-based allocations: monthly or quarterly accrual with caps
- Allow carry-over of unused days with configurable maximum carry-over limits
- Prorate allocations for mid-year joiners based on their start date
- Managers can grant additional allocations for exceptional circumstances

## Approval Workflow
- Employees submit leave requests specifying type, dates, and optional description
- Requests route to the direct manager (department manager) for first-level approval
- HR can override or approve requests that bypass the standard chain
- Notify the employee immediately upon approval or rejection with the reason
- Approved leaves automatically appear on the team calendar and reduce available balance

## Holiday Calendars
- Define public holiday calendars per country or work location
- Assign the correct public holiday calendar to each employee or company
- Public holidays are excluded from leave day calculations automatically
- Support regional variations with multiple calendars in multi-location setups
- Update public holiday calendars annually before the new fiscal year begins
