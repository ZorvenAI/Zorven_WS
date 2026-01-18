#!/bin/bash
# ==============================================================================
# Django Backend Startup Script
# Runs migrations and starts Gunicorn server
# ==============================================================================

set -e

echo "Starting AI Brand Automator Backend..."

# Wait for database to be ready
echo "Waiting for database..."
python << END
import sys
import time
import psycopg2
from urllib.parse import urlparse

database_url = "$DATABASE_URL"
if database_url:
    parsed = urlparse(database_url)
    while True:
        try:
            conn = psycopg2.connect(
                host=parsed.hostname,
                port=parsed.port or 5432,
                user=parsed.username,
                password=parsed.password,
                dbname=parsed.path[1:]
            )
            conn.close()
            print("Database is ready!")
            break
        except psycopg2.OperationalError as e:
            print(f"Database not ready yet: {e}")
            time.sleep(2)
else:
    print("No DATABASE_URL set, skipping database check")
END

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Run database migrations
echo "Running database migrations..."
python manage.py migrate --noinput

# Start Gunicorn
echo "Starting Gunicorn server on port ${PORT:-8000}..."
exec gunicorn brand_automator.wsgi:application \
    --bind 0.0.0.0:${PORT:-8000} \
    --workers ${GUNICORN_WORKERS:-4} \
    --threads ${GUNICORN_THREADS:-2} \
    --worker-class gthread \
    --worker-tmp-dir /dev/shm \
    --timeout 120 \
    --keep-alive 5 \
    --max-requests 1000 \
    --max-requests-jitter 50 \
    --access-logfile - \
    --error-logfile - \
    --capture-output \
    --log-level ${LOG_LEVEL:-info}
