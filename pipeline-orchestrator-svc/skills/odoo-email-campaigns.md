---
name: odoo-email-campaigns
version: "1.0"
description: Email marketing campaign management
target_agents:
  - odoo_mcp
triggers:
  - "email"
  - "mailing"
  - "campaign"
  - "newsletter"
  - "list"
priority: 7
max_tokens: 400
---
# Email Marketing Campaigns

## Campaign Setup
- Create campaigns as containers grouping related mailings under a single objective
- Define the campaign goal: awareness, lead generation, retention, or re-engagement
- Set campaign start and end dates to track performance within a bounded period
- Assign a responsible user for campaign oversight and reporting
- Link UTM parameters (source, medium, campaign) for downstream analytics tracking

## Mailing List Management
- Create segmented mailing lists based on customer attributes (industry, lifecycle stage, geography)
- Support opt-in via website subscription forms and opt-out via unsubscribe links
- Deduplicate contacts across lists to prevent recipients from receiving duplicates
- Clean lists periodically by removing hard bounces and long-term non-engagers
- Comply with GDPR and CAN-SPAM: include physical address and one-click unsubscribe in every email

## A/B Testing
- Test subject lines, sender names, or email content with a percentage of the audience
- Split the test group evenly (e.g., 10% variant A, 10% variant B, 80% winner)
- Define the winning metric: open rate, click rate, or reply rate
- Set the evaluation delay (recommended: 2-4 hours) before sending the winner to the remainder
- Document learnings from each A/B test to build a subject line best-practices library

## Delivery Metrics and Optimization
- Monitor key metrics: delivery rate, open rate, click-through rate, bounce rate, unsubscribe rate
- Target benchmarks: 95%+ delivery, 20%+ open rate, 3%+ click-through rate
- Investigate bounce rates above 5% -- clean list and verify sender domain authentication (SPF, DKIM, DMARC)
- Schedule sends based on audience timezone for optimal engagement
- Use the "Sent Mailings" dashboard to compare performance across campaigns over time
