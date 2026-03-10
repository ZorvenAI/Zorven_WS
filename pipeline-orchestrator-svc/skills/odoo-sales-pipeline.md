---
name: odoo-sales-pipeline
version: "1.0"
description: Sales pipeline management and lead scoring for Odoo CRM
target_agents:
  - odoo_worker
triggers:
  - "lead"
  - "pipeline"
  - "opportunity"
  - "sales funnel"
  - "conversion"
priority: 8
max_tokens: 400
---
# CRM Sales Pipeline Management

## Lead Lifecycle Stages

| Stage | Entry Criteria | Exit Criteria |
|-------|---------------|---------------|
| New | Inbound form, import, or manual entry | Qualified or marked as lost |
| Qualified | Budget, authority, need, timeline confirmed | Opportunity created |
| Proposition | Quotation sent to prospect | Quote accepted or rejected |
| Won | Signed contract or confirmed PO | Order created in Sales module |
| Lost | Prospect declines or goes silent | Lost reason recorded |

## Lead Scoring Criteria
- Assign points based on company size, industry fit, and engagement level
- Score thresholds: Hot (80+), Warm (50-79), Cold (below 50)
- Automate score updates using server actions on lead field changes
- Re-score stale leads weekly and demote inactive ones after 30 days

## Stage Progression Rules
- Never skip stages -- leads must pass through each gate sequentially
- Require a scheduled activity before moving from Qualified to Proposition
- Attach at least one quotation before transitioning to the Won stage
- Record a lost reason from the predefined list when marking a lead as Lost

## Pipeline Velocity Metrics
- Track average days-in-stage to identify bottlenecks
- Monitor conversion rate between each consecutive stage pair
- Calculate weighted pipeline value: sum of (expected revenue * probability) per stage
- Review win rate by salesperson, team, and source channel monthly
