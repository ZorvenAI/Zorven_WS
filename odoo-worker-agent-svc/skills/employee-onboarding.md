---
name: employee-onboarding
version: "1.0"
description: Create new employee records and manage onboarding process
target_personas:
  - hr_manager
triggers:
  - "new employee"
  - "onboard"
  - "hire"
  - "onboarding"
  - "create employee"
mcp_tools:
  - hr_create_employee
  - odoo_search
priority: 7
max_tokens: 400
---
# Employee Onboarding

## Workflow
1. Create the employee record with personal information (name, email, phone) using `hr_create_employee`
2. Assign the department and job position by searching available options with `odoo_search`
3. Set up the employment contract with salary details if provided
4. Return the employee ID and summary of the created record

## Important
- Search for existing employees to avoid duplicate records before creating
- Validate that the specified department and job position exist in the system
- Required fields at minimum are employee name and department
- Do not set sensitive fields like bank account details unless explicitly provided and confirmed
