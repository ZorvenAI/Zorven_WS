---
name: manage-email-marketing
version: "1.1"
description: Manage email marketing campaigns, mailing lists, and mass mailings
target_personas:
  - marketing_manager
  - general_assistant
  - sales_manager
triggers:
  - "email marketing"
  - "email campaign"
  - "mailing list"
  - "mailing lists"
  - "newsletter"
  - "mass email"
  - "mass mailing"
  - "campaign"
  - "email to customers"
  - "email to all"
  - "send email"
  - "blog to customers"
mcp_tools:
  - marketing_create_campaign
  - marketing_send_mailing
  - odoo_search_read
  - odoo_search
priority: 9
max_tokens: 500
---
# Manage Email Marketing

## CRITICAL — Tool Selection
- ALWAYS use `marketing_create_campaign` to create email campaigns
- NEVER use `website_create_page` — it does not exist and will fail
- NEVER use `odoo_create` on `mailing.mailing` — use `marketing_create_campaign` instead
- For searching customers: use `odoo_search_read` on `res.partner` with domain `[["customer_rank", ">", 0]]`

## Workflow — Send Blog/Content to Customers via Email
1. Search customers: `odoo_search_read` on `res.partner` with domain `[["customer_rank", ">", 0], ["email", "!=", false]]` and fields `["name", "email"]`
2. Get the ir.model ID: `odoo_search_read` on `ir.model` with domain `[["model", "=", "res.partner"]]` and fields `["id"]`
3. Create campaign: `marketing_create_campaign` with subject, body_html (the blog/content as HTML), and mailing_model_id (the ir.model ID from step 2)
4. Report: Return campaign ID, subject, recipient count, and status as KPI data

## Workflow — Create Campaign with Mailing List
1. Search for the target mailing list: `odoo_search_read` on `mailing.list` with fields `["name", "contact_count"]`
2. Get ir.model ID: `odoo_search_read` on `ir.model` with domain `[["model", "=", "mailing.contact"]]` and fields `["id"]`
3. Create campaign: `marketing_create_campaign` with subject, body_html, mailing_model_id, and contact_list_ids

## Workflow — List Campaigns
1. Search `mailing.mailing` with fields `["subject", "state", "sent", "delivered", "opened", "replied", "bounced"]`

## Response Format
When a campaign is created, include these KPI fields in your final answer:
- campaign_id: The ID of the created campaign
- campaign_subject: The email subject line
- campaign_status: "draft" (newly created)
- recipient_count: Number of target recipients
- action_taken: "campaign_created" or "campaign_sent"

## Important
- Use model `mailing.mailing` for campaigns, `mailing.list` for lists
- Campaign states: draft, in_queue, sending, done
- Default to creating in draft state — do NOT send unless explicitly asked
- If the blog content is in previous_outputs, use it as body_html
