---
name: odoo-project-management
version: "1.0"
description: Project task tracking and milestone management
target_agents:
  - odoo_worker
triggers:
  - "project"
  - "task"
  - "milestone"
  - "sprint"
  - "kanban"
  - "stage"
priority: 8
max_tokens: 400
---
# Project and Task Management

## Task Lifecycle
- Create tasks within projects with clear titles, descriptions, and assignees
- Set deadlines and planned hours to establish time expectations
- Track task progress through customizable Kanban stages
- Use checklists within tasks for granular subtask tracking
- Log time spent via timesheet entries linked to the task for actual vs. planned comparison

## Stage Configuration
- Define stages per project: Backlog, To Do, In Progress, Review, Done
- Set stage fold behavior to collapse completed or inactive stages in Kanban view
- Configure automatic email notifications on stage transitions
- Use stage-specific rating requests to collect customer satisfaction at completion
- Limit work-in-progress per stage to prevent team overload

## Subtasks and Dependencies
- Break large tasks into subtasks with their own assignees and deadlines
- Subtask progress rolls up to the parent task for consolidated tracking
- Define task dependencies to enforce execution order where needed
- Use the Gantt view to visualize task timelines and dependency chains
- Identify critical path tasks that directly impact the project end date

## Project Profitability
- Enable timesheet billing to convert tracked hours into invoiceable amounts
- Set billing rates per employee, role, or project for accurate revenue recognition
- Compare project revenue (billed timesheets) against costs (employee cost, expenses)
- Monitor project margin percentage on the project dashboard
- Generate profitability reports grouped by project, customer, or time period
