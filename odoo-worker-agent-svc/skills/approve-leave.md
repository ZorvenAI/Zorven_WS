---
name: approve-leave
version: "1.0"
description: Review and approve or reject employee leave requests
target_personas:
  - hr_manager
triggers:
  - "approve leave"
  - "leave request"
  - "time off"
  - "vacation"
  - "sick leave"
mcp_tools:
  - hr_get_leave_requests
  - hr_approve_leave
priority: 7
max_tokens: 350
---
# Approve Leave

## Workflow
1. Retrieve pending leave requests using `hr_get_leave_requests` filtered by status
2. Review the details including employee name, leave type, dates, and duration
3. Approve or reject the request using `hr_approve_leave` with an optional reason

## Important
- Always present the leave details to the user before taking action
- Include the remaining leave balance for the employee when available
- If rejecting, require a reason to be provided
- Handle overlapping leave requests by flagging potential conflicts
