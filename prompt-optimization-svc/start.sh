#!/bin/bash
set -e

PROCESS="${PROCESS_TYPE:-web}"

case "$PROCESS" in
  worker)
    echo "Starting Celery worker..."
    exec celery -A app.celery_app worker -l info --concurrency=2 --max-tasks-per-child=50
    ;;
  beat)
    echo "Starting Celery beat scheduler..."
    exec celery -A app.celery_app beat -l info
    ;;
  *)
    echo "Starting FastAPI web server..."
    exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8110}"
    ;;
esac
