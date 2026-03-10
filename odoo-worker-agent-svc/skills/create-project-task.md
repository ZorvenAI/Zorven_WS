---
name: create-project-task
version: "1.0"
description: Create a new task within a project and assign it to a team member
target_personas:
  - project_manager
triggers:
  - "create task"
  - "new task"
  - "assign task"
  - "project task"
mcp_tools:
  - project_create_task
  - odoo_search
priority: 7
max_tokens: 350
---
# Create Project Task

## Workflow
1. Search for the target project by name using `odoo_search` on the `project.project` model
2. Create the task with title, description, and assignee using `project_create_task`
3. Set the deadline and priority if specified by the user
4. Return the task reference and assigned user confirmation

## Important
- If no project is specified, ask the user which project the task belongs to
- Search for the assignee by name using `odoo_search` on `res.users` if a name is provided
- Set appropriate tags or stage if mentioned by the user
- Default priority is normal unless explicitly stated otherwise
