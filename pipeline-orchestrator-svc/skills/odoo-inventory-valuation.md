---
name: odoo-inventory-valuation
version: "1.0"
description: Inventory costing and valuation methods
target_agents:
  - odoo_worker
triggers:
  - "valuation"
  - "FIFO"
  - "AVCO"
  - "costing"
  - "inventory value"
priority: 7
max_tokens: 400
---
# Inventory Valuation

## Costing Methods

| Method | How Cost is Determined | Best For |
|--------|----------------------|----------|
| Standard Price | Fixed cost set manually on the product | Stable-cost manufactured goods |
| Average Cost (AVCO) | Weighted average recalculated on each receipt | High-volume commodity products |
| First In First Out (FIFO) | Cost of oldest stock layer used first | Perishable or date-sensitive goods |

## Costing Method Configuration
- Set the costing method at the product category level, not per product
- AVCO updates the cost price automatically when new stock is received at a different price
- FIFO creates discrete stock valuation layers for each incoming lot
- Standard cost requires manual price updates; use "Update Cost" wizard for batch changes
- Never change the costing method on a category with existing stock without revaluation

## Landed Costs
- Create landed cost records for freight, customs, insurance, and handling charges
- Allocate landed costs to specific receipts using quantity, value, or weight methods
- Post landed cost entries to adjust the inventory valuation account
- Include landed costs before running margin analysis to reflect true product cost
- Track landed cost per unit for import-heavy product lines

## Valuation Reports
- Run the Inventory Valuation report to see current stock value by product
- Compare valuation across periods to detect cost fluctuations
- Use the Stock Valuation Layer detail view for FIFO cost tracing
- Reconcile inventory valuation accounts with the general ledger monthly
- Investigate and resolve discrepancies before financial period close
