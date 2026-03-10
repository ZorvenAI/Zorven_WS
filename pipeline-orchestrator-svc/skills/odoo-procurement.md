---
name: odoo-procurement
version: "1.0"
description: Purchase order and vendor management
target_agents:
  - odoo_worker
triggers:
  - "purchase"
  - "RFQ"
  - "vendor"
  - "replenishment"
  - "procurement"
priority: 8
max_tokens: 400
---
# Procurement and Purchase Management

## RFQ Workflow
- Create Requests for Quotation to solicit pricing from one or more vendors
- Send RFQs via email directly from Odoo with the "Send by Email" action
- Compare multiple vendor responses using the Purchase Tender feature
- Select the best offer based on price, lead time, and payment terms
- Confirm the RFQ to convert it into a binding Purchase Order

## Vendor Evaluation
- Maintain a preferred vendor list per product with priority ranking
- Track vendor performance metrics: on-time delivery rate, quality rejection rate, price competitiveness
- Set minimum order quantities and lead times per vendor-product combination
- Review vendor scorecards quarterly and update preferred vendor assignments
- Blacklist underperforming vendors by archiving their supplier pricelist entries

## Reorder Rules
- Configure minimum stock rules (reorder points) per product and warehouse
- Set minimum quantity, maximum quantity, and order multiple for each rule
- The scheduler runs daily to generate RFQs or manufacturing orders automatically
- Use "Make to Order" routes for products that should never be stocked
- Combine reorder rules with safety stock days to buffer against lead time variability

## Purchase Agreements
- Create blanket orders for recurring purchases with negotiated pricing
- Define agreement validity periods and maximum quantities
- Generate call-off purchase orders against the blanket agreement as needed
- Track consumed vs. remaining quantities on the agreement dashboard
- Close agreements automatically when the total quantity is fully consumed
