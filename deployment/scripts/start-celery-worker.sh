#!/bin/bash
# ==============================================================================
# Celery Worker Startup Script
# Starts Celery worker with auto-scaling
# ==============================================================================

set -e

echo "Starting Celery Worker..."

# Wait for Redis to be ready
echo "Waiting for Redis..."
python << END
import sys
import time
import redis
import os

redis_url = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/0")
while True:
    try:
        r = redis.from_url(redis_url)
        r.ping()
        print("Redis is ready!")
        break
    except redis.exceptions.ConnectionError as e:
        print(f"Redis not ready yet: {e}")
        time.sleep(2)
END

# Start Celery worker
echo "Starting Celery worker..."
exec celery -A brand_automator worker \
    --loglevel=${CELERY_LOG_LEVEL:-info} \
    --concurrency=${CELERY_CONCURRENCY:-4} \
    --max-tasks-per-child=${CELERY_MAX_TASKS_PER_CHILD:-1000} \
    --prefetch-multiplier=${CELERY_PREFETCH_MULTIPLIER:-4} \
    -Q ${CELERY_QUEUES:-celery,high_priority,low_priority,ingestion,curation,orchestration}
