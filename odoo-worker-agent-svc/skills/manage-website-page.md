---
name: manage-website-page
version: "1.0"
description: Update and manage website pages and content
target_personas:
  - website_editor
triggers:
  - "website page"
  - "update page"
  - "web content"
  - "edit page"
mcp_tools:
  - website_update_page
  - odoo_search
priority: 6
max_tokens: 350
---
# Manage Website Page

## Workflow
1. Search for the existing page by name or URL using `odoo_search` on the `website.page` model
2. Update the page content, title, or SEO metadata using `website_update_page`
3. Set the publication status to published or draft as requested

## Important
- Always show the current page content before making changes so the user can confirm
- Preserve existing SEO metadata unless the user explicitly requests changes
- Validate that HTML content is well-formed before updating
- Inform the user of the page URL after updates are applied
