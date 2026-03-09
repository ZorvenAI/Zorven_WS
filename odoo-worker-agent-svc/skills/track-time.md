---
name: track-time
version: "1.0"
description: Log timesheet entries against projects and tasks
target_personas:
  - project_manager
triggers:
  - "timesheet"
  - "log time"
  - "time tracking"
  - "hours worked"
mcp_tools:
  - project_log_timesheet
  - odoo_search
priority: 6
max_tokens: 300
---
# Track Time

## Workflow
1. Find the project and task using `odoo_search` on `project.project` and `project.task`
2. Log the hours with a description of work performed using `project_log_timesheet`
3. Return the timesheet entry confirmation with total hours logged

## Important
- Require both a project and task to be specified for accurate time tracking
- Default the date to today if no date is provided
- Validate that the hours value is reasonable (e.g., not exceeding 24 hours per entry)
- Show the cumulative hours on the task after logging the new entry
