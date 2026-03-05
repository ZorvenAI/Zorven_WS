---
name: odoo-user-management
version: "1.0"
description: User accounts and access group management
target_agents:
  - odoo_mcp
triggers:
  - "user"
  - "access"
  - "group"
  - "permission"
  - "role"
priority: 8
max_tokens: 400
---
# User and Access Management

## User Creation
- Create internal users for employees and portal users for external partners/customers
- Link internal users to their employee record for HR integration
- Set the user's default company, language, and timezone upon creation
- Send a password reset invitation email to new users instead of setting passwords manually
- Deactivate user accounts immediately upon employee departure -- never delete

## Access Rights Architecture

| Layer | Scope | Configured Via |
|-------|-------|----------------|
| Access Rights | Model-level CRUD | ir.model.access CSV files |
| Record Rules | Row-level filtering | ir.rule domain expressions |
| Groups | Logical role bundles | res.groups with implied/inherited groups |
| Field-Level | Attribute visibility | groups= parameter on model fields |

## Group Assignment
- Assign users to application-level groups: User, Manager, Administrator per module
- Use group inheritance (implied_ids) so Manager automatically includes User permissions
- Create custom groups for cross-module roles (e.g., "Regional Manager" spanning Sales + Inventory)
- Audit group memberships quarterly to enforce least-privilege access
- Document the purpose of each custom group in the group description field

## Two-Factor Authentication
- Enable two-factor authentication (TOTP) for all internal users as a security best practice
- Require 2FA for users with administrator or accounting access at minimum
- Guide users through setup: scan QR code with an authenticator app
- Provide backup codes for account recovery in case of device loss
- Log 2FA enrollment status and enforce compliance through periodic access reviews
