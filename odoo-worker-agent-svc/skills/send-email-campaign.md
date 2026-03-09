---
name: send-email-campaign
version: "1.0"
description: Create and send email marketing campaigns
target_personas:
  - marketing_manager
triggers:
  - "email campaign"
  - "mailing"
  - "newsletter"
  - "mass email"
  - "campaign"
mcp_tools:
  - marketing_create_campaign
  - odoo_search
priority: 6
max_tokens: 350
---
# Send Email Campaign

## Workflow
1. Define the campaign target audience by searching mailing lists or contact segments using `odoo_search`
2. Create the mailing with subject line, body content, and recipient list using `marketing_create_campaign`
3. Schedule the campaign for a specific date/time or send immediately as requested

## Important
- Always confirm the recipient count before sending to prevent unintended mass emails
- Require a subject line and body content before creating the campaign
- Default to scheduling rather than immediate send unless the user explicitly says to send now
- Warn the user if the recipient list is empty or unusually large
