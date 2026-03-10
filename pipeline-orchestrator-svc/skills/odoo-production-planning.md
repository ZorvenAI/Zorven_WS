---
name: odoo-production-planning
version: "1.0"
description: Manufacturing production planning and BOM management
target_agents:
  - odoo_worker
triggers:
  - "BOM"
  - "manufacturing"
  - "production"
  - "work order"
  - "MRP"
priority: 8
max_tokens: 400
---
# Production Planning and Manufacturing

## Bill of Materials Structure
- Define BOMs at the product level with component lines and quantities
- Support multi-level BOMs where components are themselves manufactured (phantom BOMs)
- Use BOM variants to handle product attribute-specific material lists
- Specify component consumption as fixed or variable (per-unit scaling)
- Version BOMs by creating new revisions rather than editing active ones

## Routing and Work Centers
- Define work centers representing machines, stations, or labor groups
- Set capacity (units per hour), cost per hour, and efficiency percentage per work center
- Create routings as ordered sequences of operations linked to work centers
- Attach routings to BOMs to generate work orders during manufacturing
- Use time tracking on work orders to compare planned vs. actual operation duration

## Production Scheduling
- Create manufacturing orders manually or let the MRP scheduler generate them
- Schedule production based on demand from sales orders and reorder rules
- Prioritize manufacturing orders by deadline date and customer priority
- Use the Gantt view for visual production scheduling across work centers
- Split large manufacturing orders into smaller batches for parallel processing

## MRP Run
- The MRP scheduler evaluates demand, supply, and reorder rules to propose actions
- Outputs include: planned manufacturing orders, purchase RFQs, and transfer requests
- Run MRP daily or on-demand after significant demand changes
- Review the MRP report for unresolved shortages and take corrective action
- Confirm planned orders to convert them into actionable manufacturing or purchase orders
