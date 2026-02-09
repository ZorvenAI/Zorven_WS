---
name: debug-pipeline
description: Debug and troubleshoot the data pipeline (ingestion → curation → RAG)
triggers:
  - "pipeline is stuck"
  - "ingestion not working"
  - "curation failed"
  - "RAG sync broken"
  - "Kafka consumer error"
---

# Skill: Debug Pipeline

## When to Use

Use this skill when the user reports issues with the data processing pipeline — file uploads not being processed, curation failing, or documents not syncing to Vertex AI.

## Diagnostic Steps

### 1. Check Pipeline Status

```bash
# Check if Kafka consumers are running
cd ai-brand-automator
python manage.py run_ingestion --check
python manage.py run_curation_consumer --check
python manage.py consume_sync_events --check
```

### 2. Check Celery Workers

```bash
# Are workers running?
celery -A brand_automator inspect active
celery -A brand_automator inspect reserved

# Check specific queues
celery -A brand_automator inspect active -Q ingestion
celery -A brand_automator inspect active -Q curation
```

### 3. Check Kafka Topics

Look for messages backing up:
```bash
# Check if KAFKA_CONSUMERS_ENABLED is true
python -c "from decouple import config; print(config('KAFKA_CONSUMERS_ENABLED', default='false'))"
```

### 4. Check GCS Access

```bash
# Verify GCS credentials are configured
python -c "from files.services import GCSService; svc = GCSService(); print(svc.bucket.name)"
```

### 5. Common Failure Points

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Upload succeeds but no processing | `KAFKA_CONSUMERS_ENABLED=false` | Set to `true` and restart consumers |
| Ingestion error: "invalid file type" | MIME type not in allowed list | Check `data_ingestion/domain/models.py` for allowed types |
| Curation timeout | Large file + Gemini API slow | Check AI service timeout settings |
| RAG sync fails | Vertex AI credentials missing | Verify `GOOGLE_APPLICATION_CREDENTIALS` env var |
| "KafkaException" in logs | Kafka broker unreachable | Check `KAFKA_BOOTSTRAP_SERVERS` config |

### 6. Log Files

```bash
# Check logs directory
ls -la ai-brand-automator/logs/

# Tail specific logs
tail -f logs/ingestion.log
tail -f logs/curation.log
```

## Recovery Actions

### Retry Failed Ingestion
```python
from data_ingestion.services import IngestionService
service = IngestionService.create()
service.retry_failed(company_id=<id>)
```

### Requeue for Curation
```python
from media_curation.services import CurationService
service = CurationService.create()
service.requeue(asset_id=<id>)
```

### Force RAG Sync
```python
from rag_index.services import RAGIndexService
service = RAGIndexService.create()
service.sync_document(document_id=<id>)
```
