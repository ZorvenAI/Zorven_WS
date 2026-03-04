---
name: odoo-time-tracking
version: "1.0"
description: Timesheet entry and billing rate management
target_agents:
  - odoo_mcp
triggers:
  - "timesheet"
  - "hours"
  - "billing rate"
  - "time tracking"
priority: 7
max_tokens: 400
---
# Time Tracking and Timesheets

## Timesheet Entry Rules
- Employees log time daily against specific projects and tasks
- Each entry requires: project, task, date, hours, and optional description
- Enforce minimum description length for entries exceeding 2 hours
- Use the timer widget for real-time tracking or manual entry for retrospective logging
- Managers can view and edit team timesheets within their department scope

## Billing Rate Configuration

| Rate Level | Applies To | Precedence |
|-----------|-----------|------------|
| Employee | Specific employee | Highest |
| Role/Job Position | All employees in a role | Medium |
| Project | All work on a project | Lower |
| Company Default | Fallback rate | Lowest |

- Configure billing rates at the most specific level that applies
- Use cost rates separately from billing rates to calculate margins
- Review and adjust rates at contract renewal or annually

## Overtime Calculation
- Define standard working hours per employee via their work schedule
- Flag timesheet entries exceeding the daily or weekly standard threshold
- Apply overtime multipliers (1.5x, 2.0x) based on company policy and jurisdiction
- Separate overtime into categories: weekday, weekend, and public holiday
- Include validated overtime in payroll input for compensation calculation

## Project Allocation
- Assign planned hours per employee per project for capacity planning
- Compare allocated hours against actual timesheet entries weekly
- Identify over-allocated employees and redistribute workload proactively
- Use the allocation Gantt chart for visual resource planning across projects
- Forecast remaining effort based on burn-down of planned vs. actual hours
