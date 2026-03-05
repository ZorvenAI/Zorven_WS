---
name: odoo-employee-management
version: "1.0"
description: Employee records and organizational structure
target_agents:
  - odoo_mcp
triggers:
  - "employee"
  - "department"
  - "job"
  - "org chart"
  - "contract"
priority: 8
max_tokens: 400
---
# Employee Management

## Employee Lifecycle
- Create employee records during onboarding with personal and work information
- Link employees to their Odoo user accounts for system access
- Track employee status: New, Probation, Active, On Notice, Archived
- Update work location, department, and manager as organizational changes occur
- Archive employee records upon departure -- never delete to preserve historical data

## Department Hierarchy
- Structure departments in a parent-child tree reflecting the organization chart
- Assign a department manager who serves as the default approver for requests
- Use department membership to control visibility of leaves, expenses, and timesheets
- Generate the organization chart visualization from the department hierarchy
- Keep department names concise and consistent across the system

## Job Positions and Titles
- Define job positions with expected headcount for recruitment planning
- Distinguish between job position (the role) and job title (the displayed name)
- Track current vs. expected employees per position to identify staffing gaps
- Link job positions to recruitment campaigns for seamless hiring workflows
- Review and update job descriptions annually to reflect evolving responsibilities

## Contract Management
- Create employment contracts with start date, salary, and working schedule
- Support multiple contract types: Full-time, Part-time, Freelance, Intern
- Track contract status: New, Running, Expired, Cancelled
- Set contract end dates for fixed-term agreements and configure expiry alerts
- Link contracts to salary structures for automated payroll computation
- Maintain contract history to provide a complete employment timeline per employee
