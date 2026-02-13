# Python base image
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    build-essential \
    libpq-dev \
    librdkafka-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Create logs and staticfiles directory
RUN mkdir -p logs staticfiles

# Expose port
EXPOSE 8000

# Create entrypoint script - v4 with GCS credentials + Kafka consumer support
RUN cat <<'EOF' > /app/entrypoint.sh && chmod +x /app/entrypoint.sh
#!/bin/bash
set -e

# Write GCS credentials file from env var if provided (Railway/Heroku)
if [ -n "$GCS_CREDENTIALS_JSON" ]; then
  echo "=== Writing GCS credentials file ==="
  printf '%s' "$GCS_CREDENTIALS_JSON" > /app/gcs-credentials.json
  chmod 600 /app/gcs-credentials.json
  export GS_CREDENTIALS_PATH=/app/gcs-credentials.json
  export GOOGLE_APPLICATION_CREDENTIALS=/app/gcs-credentials.json
fi

echo "=== Running migrations ==="
python manage.py migrate_schemas --shared --noinput
echo "=== Bootstrapping public tenant ==="
python create_public_tenant.py
echo "=== Setting up production domains ==="
python add_production_domains.py
echo "=== Running membership migration (idempotent) ==="
python scripts/migrate_to_membership.py --apply || echo "Membership migration skipped or already done"
echo "=== Provisioning tenant GCS buckets (idempotent) ==="
python scripts/provision_tenant_buckets.py --apply || echo "Bucket provisioning skipped or already done"
echo "=== Collecting static files ==="
python manage.py collectstatic --noinput || true
echo "=== Starting Gunicorn on port $PORT ==="
exec gunicorn brand_automator.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --threads 2 --timeout 120 --access-logfile - --error-logfile -
EOF

# Create worker entrypoint (for Kafka consumers and Celery workers on Railway)
RUN cat <<'EOF' > /app/entrypoint-worker.sh && chmod +x /app/entrypoint-worker.sh
#!/bin/bash
set -e

# Write GCS credentials file from env var if provided (Railway/Heroku)
if [ -n "$GCS_CREDENTIALS_JSON" ]; then
  printf '%s' "$GCS_CREDENTIALS_JSON" > /app/gcs-credentials.json
  chmod 600 /app/gcs-credentials.json
  export GS_CREDENTIALS_PATH=/app/gcs-credentials.json
  export GOOGLE_APPLICATION_CREDENTIALS=/app/gcs-credentials.json
fi

# Execute the command passed as arguments
exec "$@"
EOF

# Run entrypoint
CMD ["/app/entrypoint.sh"]
