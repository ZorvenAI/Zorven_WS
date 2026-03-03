---
name: ingestion-bridge
version: "1.0"
description: Data ingestion pipeline payload formatting and tenant routing
target_agents:
  - rag_uploader
triggers:
  - "upload"
  - "ingest"
  - "archive"
  - "pipeline"
  - "rag"
  - "knowledge base"
  - "store"
  - "index"
priority: 8
max_tokens: 350
---
# IngestionBridge — Pipeline Payload Formatting

## Purpose
Format document payloads to match the exact schema expected by the
data-ingestion-svc and ensure files land in the correct tenant-scoped
GCS path.

## Tenant Routing Rules
- Always inject X-Tenant-ID into Kafka message headers
- Files must land in the `{tenant_id}/raw/` GCS path prefix
- Verify tenant_id is present before emitting any event — skip with warning if missing
- Use tenant_context from the pipeline state as the authoritative source

## IngestionEvent Schema Requirements
- event_id: UUID v4 (unique per event)
- trace_id: UUID v4 (for distributed tracing, reuse pipeline job_id when available)
- timestamp: ISO 8601 UTC format
- source: "api-integration" for pipeline-originated uploads
- tenant_id: Must match the X-Tenant-ID header
- file_path: Full GCS URI (gs://bucket/tenant_id/raw/filename)
- file_type: MIME type of the file
- file_size_bytes: Size in bytes (null if unknown)
- metadata: Dict with custom_title, original_name, source, job_id

## Deduplication
- Check Redis before emitting (hash the GCS URI)
- Mark as ingested after successful emit
- Skip duplicates silently with a log entry

## Error Handling
- Kafka send failures are non-fatal — log and return False
- Never block the pipeline on ingestion failures
- Include the trace_id in all log messages for debugging
