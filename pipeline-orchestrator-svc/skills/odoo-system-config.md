---
name: odoo-system-config
version: "1.0"
description: System settings and module configuration
target_agents:
  - odoo_mcp
triggers:
  - "setting"
  - "config"
  - "module"
  - "install"
  - "technical"
priority: 7
max_tokens: 400
---
# System Configuration

## Module Installation
- Install modules from the Apps menu by searching and clicking "Install"
- Review module dependencies before installation -- Odoo installs them automatically
- Test new module installations in a staging database before applying to production
- Update the module list after deploying custom modules to the addons path
- Uninstall unused modules to reduce system complexity and attack surface

## System Parameters
- Access technical parameters via Settings > Technical > Parameters > System Parameters
- Use system parameters for feature flags and configuration values (key-value pairs)
- Common parameters: `web.base.url`, `mail.catchall.domain`, `database.expiration_date`
- Prefix custom parameters with a namespace (e.g., `custom.my_feature.enabled`)
- Never store secrets in system parameters -- use environment variables or the Odoo vault

## Scheduled Actions (Cron Jobs)
- View and manage scheduled actions under Settings > Technical > Automation > Scheduled Actions
- Configure execution interval: minutes, hours, days, weeks, or months
- Set the "Number of Calls" to -1 for recurring actions or a positive integer for finite runs
- Monitor the "Last Execution" timestamp and "Next Execution" schedule for each action
- Disable non-essential scheduled actions in development environments to reduce noise

## Database Management
- Use the database manager (/web/database/manager) for backup, restore, and duplication
- Schedule automated daily backups with off-site storage for disaster recovery
- Duplicate the production database to staging before major upgrades or module installs
- Set a strong master password on the database manager to prevent unauthorized access
- Monitor database size growth and plan storage capacity proactively
