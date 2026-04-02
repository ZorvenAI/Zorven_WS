---
name: ad-publishing-account-validator
version: "1.0"
description: Validate Meta Ads account access, permissions, payment method, and Special Ad Category settings before campaign creation (maps to SKL-APA33-02)
target_agents:
  - ad_publishing
triggers:
  - "validate meta account"
  - "check ad account permissions"
  - "meta ads account setup"
  - "verify ad account"
priority: 9
max_tokens: 600
---

# Account Validator

## Purpose
Verify that the configured Meta Ads account is accessible, has the required permissions for campaign management, has a valid payment method on file, and has correct Special Ad Category settings. This gate prevents downstream campaign creation failures caused by account misconfiguration or insufficient permissions.

## Methodology

### 1. Resolve Meta API Credentials
From `node_outputs.apa_context.meta_account`:
- Decrypt the stored access token via the tenant credential vault
- Construct the Meta Marketing API base URL: `https://graph.facebook.com/v21.0/`
- Set the Ad Account ID in `act_XXXXXXX` format

### 2. Validate Ad Account Access
Call `GET /{ad_account_id}?fields=account_status,name,currency,timezone_name,business`:
- Confirm `account_status == 1` (ACTIVE); reject DISABLED (2), UNSETTLED (3), PENDING_RISK_REVIEW (7)
- Verify the account currency matches the CAA blueprint budget currency
- Record timezone for scheduling alignment

### 3. Check Account Permissions
Call `GET /{ad_account_id}/assigned_users?fields=permissions`:
- Require at minimum: `MANAGE_CAMPAIGNS`, `MANAGE_ADS` permissions
- For budget operations: verify `MANAGE_FUNDING_SOURCE` permission
- Log warning if `ANALYZE_PERFORMANCE` is absent (affects post-publish verification)

### 4. Validate Payment Method
Call `GET /{ad_account_id}/adspixels` and `GET /{ad_account_id}/funding_source_details`:
- Confirm at least one active funding source exists
- Verify funding source is not expired or declined
- In sandbox mode, skip payment validation (sandbox uses test billing)

### 5. Verify Special Ad Category Configuration
If `apa_context.special_ad_category` is set:
- Confirm the ad account has accepted the Special Ad Category terms
- Validate that the declared category matches any account-level restrictions
- Flag if housing/credit/employment category requires restricted targeting (no age, gender, ZIP targeting)

### 6. Validate Facebook Page
Call `GET /{page_id}?fields=id,name,access_token,is_published`:
- Confirm the Page exists and is published
- Verify the access token has `pages_manage_ads` permission on this Page
- Record Page name for ad identity

## Output Schema
Write to `node_outputs.apa_account_validation` with keys:
- `account_id`: string (act_XXXXXXX)
- `account_name`: string
- `account_status`: string (ACTIVE)
- `currency`: string (ISO 4217)
- `timezone`: string (IANA timezone)
- `page_id`: string
- `page_name`: string
- `permissions`: list[str] (granted permissions)
- `has_payment_method`: boolean
- `special_ad_category_verified`: boolean
- `sandbox_mode`: boolean
- `validation_passed`: boolean
- `validation_warnings`: list[str]
- `validation_errors`: list[str]

## Integration Notes
- If `validation_passed` is false, the pipeline halts and returns errors to the Django callback for user remediation
- Sandbox mode bypasses payment validation but still verifies account access and permissions
- The validated `account_id` and `page_id` are used by all downstream entity creation skills (SKL-APA33-03 through SKL-APA33-09)
