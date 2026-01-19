#!/bin/bash
# ==============================================================================
# Celery Beat Scheduler Startup Script
# Starts Celery Beat for periodic tasks
# ==============================================================================

set -e

echo "Starting Celery Beat Scheduler..."

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

# Remove stale pidfile if exists
rm -f /app/celerybeat/celerybeat.pid

# Start Celery Beat
echo "Starting Celery Beat..."
exec celery -A brand_automator beat \
    --loglevel=${CELERY_LOG_LEVEL:-info} \
    --pidfile=/app/celerybeat/celerybeat.pid \
    --schedule=/app/celerybeat/celerybeat-schedule
