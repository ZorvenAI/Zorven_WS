---
name: user-management
version: "1.0"
description: Create and manage user accounts, access rights, and permissions
target_personas:
  - it_admin
triggers:
  - "create user"
  - "new user"
  - "user access"
  - "permissions"
  - "reset password"
mcp_tools:
  - admin_create_user
  - admin_update_access
  - odoo_search
priority: 6
max_tokens: 400
---
# User Management

## Workflow
1. Create a new user account or find an existing user using `admin_create_user` or `odoo_search` on `res.users`
2. Assign security groups and access rights using `admin_update_access`
3. Configure additional security settings such as two-factor authentication if requested

## Important
- Never display or log passwords in plain text
- Verify that the requested access groups exist before assignment
- Warn before granting administrative or elevated privileges
- Check for existing users with the same email to prevent duplicate accounts
