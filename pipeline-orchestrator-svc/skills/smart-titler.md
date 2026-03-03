---
name: smart-titler
version: "1.0"
description: Generate professional descriptive filenames for generic document uploads
target_agents:
  - rag_uploader
triggers:
  - "upload"
  - "document"
  - "file"
  - "archive"
  - "rag"
  - "knowledge base"
  - "store"
  - "index"
priority: 10
max_tokens: 350
---
# SmartTitler — Descriptive Filename Generation

## Purpose
Ensure the RAG knowledge base remains organized with human-readable titles
instead of generic filenames like "upload.pdf" or "document1.docx".

## Naming Rules
- Generate exactly 3 to 5 words that describe the document's content
- Use professional, descriptive language (e.g., "Q4 Revenue Analysis Report")
- Include the document type when relevant (Report, Guide, Policy, Brief, etc.)
- Include company or brand names if they appear in the content
- Include dates or time periods if the content is time-specific

## GCS Compatibility Constraints
- No spaces — use underscores instead
- No special characters (only alphanumeric and underscores)
- No consecutive underscores
- Maximum 200 characters for the base name (excluding extension)
- Preserve the original file extension

## Examples
| Generic Name | Content Hint | Smart Title |
|-------------|-------------|-------------|
| upload.pdf | Q4 2024 revenue figures | Q4_2024_Revenue_Analysis_Report.pdf |
| document1.docx | Brand guidelines | Brand_Identity_Guidelines_Manual.docx |
| IMG_4521.png | Company logo variants | Company_Logo_Variant_Collection.png |
| file.csv | Customer survey responses | Customer_Survey_Response_Data.csv |

## When NOT to Rename
- If the filename is already descriptive (not matching generic patterns)
- If the content preview is empty or unreadable (binary without text)
- Return the original slugified name in these cases
