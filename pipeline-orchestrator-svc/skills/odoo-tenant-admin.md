---
name: odoo-tenant-admin
version: "1.0"
description: Tenant provisioning and database management
target_agents:
  - odoo_worker
triggers:
  - "tenant"
  - "provision"
  - "database"
  - "company"
  - "multi-company"
priority: 8
max_tokens: 400
---
# Tenant and Multi-Company Administration

## Database Provisioning
- Create new tenant databases via the database manager or automated provisioning API
- Apply a standardized template database with pre-configured modules and master data
- Set the database name, admin credentials, default language, and country during creation
- Install the required module set immediately after provisioning to establish baseline functionality
- Verify the new database is accessible and functional before handing off to the tenant

## Company Setup
- Configure the company record with legal name, address, tax ID, and logo
- Set the company currency, fiscal year, and chart of accounts template
- Define the company's bank accounts for payment processing and reconciliation
- Configure email servers (outgoing SMTP and incoming IMAP) per company
- Establish the default warehouse, stock locations, and operational sequences

## Inter-Company Rules
- Enable inter-company transactions for multi-company environments
- Configure automatic creation of purchase orders in Company B when Company A creates a sales order
- Set inter-company pricing rules: at cost, with markup, or at public pricelist prices
- Reconcile inter-company balances monthly using the inter-company journal
- Restrict inter-company document creation to authorized users only

## Tenant Isolation
- Each tenant operates in its own database with full data isolation
- Configure separate domains or subdomains per tenant using the `db_filter` parameter
- Enforce resource limits (storage, users) per tenant based on subscription tier
- Maintain separate backup schedules and retention policies per tenant database
- Monitor tenant database sizes and user counts for capacity planning and billing
