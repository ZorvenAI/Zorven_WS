---
name: odoo-data-export-import
version: "1.0"
description: Data migration and CSV export/import
target_agents:
  - odoo_worker
triggers:
  - "export"
  - "import"
  - "CSV"
  - "data migration"
  - "transfer"
priority: 7
max_tokens: 400
---
# Data Export and Import

## Export Formats
- Use the list view "Export" button to generate CSV or XLSX files from any model
- Select fields manually or use saved export templates for recurring exports
- Export the External ID (XML ID) column to enable re-import and record matching
- For relational fields, export the related record's name or External ID, not the raw database ID
- Large exports (100k+ records) should use the ORM `export_data` method via RPC for performance

## Import Mapping
- Prepare CSV files with column headers matching Odoo field names or labels
- Use the import preview screen to map columns to fields and review sample data
- Match existing records using External ID or a unique field (e.g., email, product code)
- Handle relational fields by referencing the related record's External ID or name
- Use "/" notation for sub-fields (e.g., "Address/City" for partner address components)

## Data Validation
- Run the import in test mode first to identify errors before committing
- Common validation errors: missing required fields, invalid relational references, wrong data types
- Fix date format mismatches by standardizing to YYYY-MM-DD before import
- Validate numeric fields have no currency symbols, commas, or text characters
- Review the error log line-by-line and correct the source CSV before re-importing

## Batch Processing
- Split large imports (50k+ rows) into smaller batches of 5,000-10,000 records
- Import master data first (contacts, products) before transactional data (invoices, orders)
- Maintain an import sequence log tracking which files were imported and when
- Verify record counts post-import: compare source file row count against Odoo record count
- Run data integrity checks after import: validate totals, spot-check random records, verify relationships
