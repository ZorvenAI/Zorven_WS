---
name: odoo-social-publishing
version: "1.0"
description: Social media content scheduling and publishing
target_agents:
  - odoo_mcp
triggers:
  - "social"
  - "post"
  - "schedule"
  - "platform"
  - "social media"
priority: 7
max_tokens: 400
---
# Social Media Publishing

## Platform Integration
- Connect social media accounts: Facebook Pages, Instagram Business, Twitter/X, LinkedIn Company Pages
- Authenticate each account via OAuth and maintain active token refresh
- Verify posting permissions after each connection to catch access issues early
- Use separate social accounts per brand or business unit in multi-company setups
- Re-authorize connections quarterly to prevent token expiration disruptions

## Post Scheduling
- Create posts with text, images, or video and assign them to one or more connected accounts
- Schedule posts for future publication by setting a specific date and time
- Use the calendar view to visualize the publishing schedule across all platforms
- Avoid scheduling conflicts: do not post to the same account more than twice per day
- Queue posts in advance for the upcoming week during a dedicated content planning session

## Engagement Metrics
- Track post-level metrics: impressions, reach, likes, comments, shares, clicks
- Monitor account-level follower growth and engagement rate trends
- Compare performance across platforms to identify the highest-ROI channels
- Identify top-performing content formats (image, video, carousel, text-only)
- Export engagement data monthly for inclusion in marketing performance reports

## Content Calendar Best Practices
- Maintain a 2-week content buffer to avoid last-minute posting
- Balance content pillars: educational (40%), promotional (20%), entertaining (20%), community (20%)
- Align social content with email campaigns and blog publications for cross-channel amplification
- Tag posts with campaign labels for aggregated campaign-level analytics
- Review and adjust the content calendar weekly based on engagement trends and upcoming events
