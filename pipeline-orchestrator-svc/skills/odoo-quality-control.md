---
name: odoo-quality-control
version: "1.0"
description: Quality inspection and control point management
target_agents:
  - odoo_worker
triggers:
  - "quality"
  - "QC"
  - "inspection"
  - "defect"
  - "check"
priority: 7
max_tokens: 400
---
# Quality Control Management

## Quality Check Types

| Check Type | Description | Typical Use |
|-----------|-------------|-------------|
| Pass/Fail | Binary accept or reject | Visual inspection, go/no-go gauge |
| Measure | Numeric measurement against tolerance | Dimensions, weight, temperature |
| Take a Picture | Photographic evidence capture | Surface finish, packaging condition |
| Text | Free-form observation notes | Detailed defect description |

## Control Point Configuration
- Define control points to trigger quality checks automatically at specific operations
- Attach control points to picking types (Receipt, Delivery) or manufacturing operations
- Set check frequency: every operation, every Nth operation, or randomly by percentage
- Specify the responsible quality team and default assignee per control point
- Link control points to specific products, product categories, or all products

## Quality Alert Management
- Create quality alerts when inspections reveal defects or non-conformances
- Assign severity levels: Low, Medium, High, Critical
- Route alerts to the quality team with a corrective action deadline
- Track root cause analysis using predefined categories (material, process, equipment, human)
- Close alerts only after corrective actions are implemented and verified

## Continuous Improvement
- Review quality check pass/fail rates by product, vendor, and work center
- Identify repeat defect patterns and implement preventive actions
- Set quality KPIs: first-pass yield, defect rate per million, inspection cycle time
- Conduct periodic quality audits and log findings in the quality alert system
- Use statistical process control trends to detect drift before failures occur
