---
name: odoo-pricing-strategy
version: "1.0"
description: Pricing, discounts, and pricelist management
target_agents:
  - odoo_mcp
triggers:
  - "price"
  - "discount"
  - "pricelist"
  - "loyalty"
  - "margin"
priority: 7
max_tokens: 400
---
# Pricing and Pricelist Management

## Pricelist Configuration
- Create pricelists per customer segment (Retail, Wholesale, VIP)
- Support multiple computation methods: fixed price, percentage discount, formula-based
- Set date-range validity for seasonal or promotional pricing
- Chain pricelists using the "Other Pricelist" computation for layered discounts
- Assign default pricelists to customer records for automatic application

## Discount Policies
- Use per-product-line discounts visible on the quotation for transparency
- Apply global discounts via pricelist rules to keep line items clean
- Configure minimum quantity thresholds for volume-based discounts
- Prevent margin erosion by setting minimum price floors on pricelist rules

## Loyalty and Rewards Programs
- Define point-based loyalty programs tied to product categories
- Configure reward tiers: free product, percentage discount, or fixed amount
- Set expiration periods on earned loyalty points (recommended: 12 months)
- Track redemption rates to evaluate program effectiveness

## Margin Analysis
- Compare sale price against product cost price on every order line
- Use the margin percentage field to flag low-margin deals below threshold
- Generate margin reports grouped by product category and salesperson
- Review landed cost impact on margins for imported goods
