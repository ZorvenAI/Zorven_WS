---
name: social-tenant-orchestrator
version: "1.0"
description: Tenant-aware social publishing with role-based approval flow
target_agents:
  - social_promoter
triggers:
  - "publish"
  - "post"
  - "social"
  - "promote"
  - "schedule"
  - "draft"
  - "linkedin"
  - "twitter"
  - "facebook"
  - "instagram"
priority: 12
max_tokens: 400
---
# Social Tenant Orchestrator — Role-Based Publishing

## Purpose
Orchestrate social media publishing with tenant-scoped permissions,
ensuring editors get approval gates while admins/owners can publish directly.

## Role-Based Flow

### ADMIN / OWNER
1. Generate platform-specific post from blog content
2. Call create_platform_draft via MCP to create the content record
3. Immediately proceed to post_to_social — no approval gate needed
4. Log the publish action to the social audit trail

### EDITOR
1. Generate platform-specific post from blog content
2. Call create_platform_draft via MCP to store as draft
3. PAUSE — do NOT publish directly
4. Store the draft for admin review and approval
5. Log as "draft_stored" in the audit trail
6. Include a finding: "Content saved as drafts for admin approval"

### VIEWER
- Reject with 403 — viewers cannot publish social content
- Do not generate any content for viewers

## MCP Integration Rules
- Always pass user_email to MCP for identity tracking
- Include X-Tenant-ID in all MCP calls for tenant routing
- Use create_scheduled_content for both immediate and scheduled posts
- For immediate publish: set scheduled_date to current UTC time, then call publish_content_now
- For scheduled publish: set scheduled_date to the resolved future time

## Content Adaptation
- Each platform gets its own adapted post — never copy-paste across platforms
- Respect platform character limits strictly
- Include hashtags appropriate to the platform
- For analysis/metrics content, translate numbers into business impact language
- For blog content, extract the key insight and create an engaging hook

## Error Handling
- MCP failures are non-fatal — log and report as "failed" per platform
- Acquire post locks before publishing to prevent duplicates
- Release locks after publish attempt regardless of success/failure
- If some platforms succeed and others fail, report both in findings
