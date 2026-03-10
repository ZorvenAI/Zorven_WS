---
name: odoo-ecommerce-ops
version: "1.0"
description: E-commerce operations and online sales
target_agents:
  - odoo_worker
triggers:
  - "ecommerce"
  - "cart"
  - "checkout"
  - "catalog"
  - "online"
  - "shop"
priority: 7
max_tokens: 400
---
# E-Commerce Operations

## Product Catalog
- Publish products to the online shop with descriptions, images, and pricing
- Use product variants (size, color, material) to manage options on a single product page
- Organize the catalog with hierarchical e-commerce categories for browsing and filtering
- Set "Available in POS" and "Available on Website" toggles independently per product
- Display stock availability status on product pages to set customer expectations

## Cart Management
- Enable guest checkout alongside registered customer checkout for conversion flexibility
- Apply promotional coupon codes and automatic discount rules at the cart level
- Show real-time shipping cost estimates based on delivery address and carrier rates
- Implement abandoned cart recovery with automated email reminders after 1 hour and 24 hours
- Allow customers to save carts and return to complete the purchase later

## Checkout Flow
- Streamline checkout to minimize steps: cart review, shipping, payment, confirmation
- Support multiple payment providers: credit card (Stripe, Adyen), PayPal, bank transfer
- Validate billing and shipping addresses with required field enforcement
- Display order summary with itemized totals (subtotal, tax, shipping, discount, total)
- Send order confirmation email immediately upon successful payment

## Shipping Integration
- Configure shipping carriers with rate calculation methods (fixed, weight-based, carrier API)
- Offer multiple shipping options at checkout: standard, express, free above threshold
- Generate shipping labels and tracking numbers from confirmed delivery orders
- Publish tracking links to the customer portal for self-service shipment tracking
- Set delivery lead time expectations per carrier and display estimated arrival dates
