---
name: process-receipt
version: "1.0"
description: Process and validate incoming goods receipts
target_personas:
  - warehouse_manager
triggers:
  - "receipt"
  - "receive goods"
  - "incoming shipment"
  - "validate receipt"
mcp_tools:
  - inventory_validate_receipt
  - odoo_search
priority: 7
max_tokens: 350
---
# Process Receipt

## Workflow
1. Find the incoming transfer or picking by reference or PO number using `odoo_search` on the `stock.picking` model
2. Verify the quantities received against the expected quantities
3. Validate the receipt using `inventory_validate_receipt` to update stock levels
4. Report the updated stock status and any discrepancies

## Important
- Filter picks by type to only show incoming receipts (picking_type_code = 'incoming')
- Flag any quantity discrepancies between expected and received amounts
- Handle backorders if partial quantities are received
- Confirm with the user before validating if there are quantity mismatches
