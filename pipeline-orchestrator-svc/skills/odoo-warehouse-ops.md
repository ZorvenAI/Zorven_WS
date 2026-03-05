---
name: odoo-warehouse-ops
version: "1.0"
description: Warehouse operations and stock transfer management
target_agents:
  - odoo_mcp
triggers:
  - "stock"
  - "picking"
  - "transfer"
  - "warehouse"
  - "delivery"
  - "shipment"
priority: 8
max_tokens: 400
---
# Warehouse Operations

## Reception Workflow
- Process incoming shipments against purchase orders using the Receipts picking type
- Validate received quantities against PO lines and flag discrepancies
- Apply lot/serial number tracking at reception for traceable products
- Use barcode scanning to accelerate receipt validation and reduce errors
- Route received goods to quality inspection or directly to stock based on product rules

## Delivery Order Processing
- Delivery orders are auto-created when sales orders are confirmed
- Pick products from designated source locations (stock, shelf, bin)
- Support multi-step delivery: Pick > Pack > Ship for complex warehouses
- Print shipping labels and carrier tracking numbers from the delivery order
- Mark as done only after physical shipment confirmation

## Inter-Warehouse Transfers
- Create internal transfer requests between warehouse locations
- Use resupply routes to automate transfers when stock drops below minimum
- Track transit inventory in a dedicated "Inter-Warehouse Transit" location
- Require two-step validation: source warehouse ships, destination warehouse receives

## Location Management
- Organize locations hierarchically: Warehouse > Zone > Shelf > Bin
- Assign default source and destination locations per operation type
- Use location-specific removal strategies (FIFO, LIFO, closest location)
- Restrict location access by warehouse team using stock access rules

## Push and Pull Rules
- **Pull rules**: Triggered by demand (sales order, MO) to procure from source
- **Push rules**: Triggered by reception to route goods to the next location automatically
- Chain rules for multi-step flows: Receive > QC > Stock > Pick > Pack > Ship
- Test route configurations with a sample product before applying globally
