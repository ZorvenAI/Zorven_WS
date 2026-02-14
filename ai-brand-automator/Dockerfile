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

# Always show which database-related env vars are available (names only, no values)
echo "=== Database Environment Check ==="
echo "Database-related env vars set in this container:"
if env | grep -qiE '^DATABASE|^DB_|^PG|^POSTGRES'; then
  env | grep -iE '^DATABASE|^DB_|^PG|^POSTGRES' | cut -d= -f1 | sort
else
  echo "  (none found)"
fi
echo "---"

# Always run database URL diagnostic — this is critical for debugging
echo "=== Database URL Diagnostic ==="
python scripts/check_database_url.py || echo "WARNING: Diagnostic script failed (non-fatal)"

# Validate DATABASE_URL is usable before running migrations
python -c "
import os, urllib.parse
raw = os.environ.get('DATABASE_URL', '')
cleaned = raw.strip().replace('\ufeff','').replace('\x00','')
cleaned = ''.join(ch for ch in cleaned if ch not in '\n\r\t')
if raw and not cleaned:
    print('FATAL: DATABASE_URL is set but contains only whitespace/control chars!')
    exit(1)
if cleaned:
    parsed = urllib.parse.urlsplit(cleaned)
    if not parsed.scheme:
        print(f'FATAL: DATABASE_URL has no scheme. Raw len={len(raw)}, cleaned={repr(cleaned[:30])}...')
        exit(1)
    if not parsed.hostname:
        print(f'FATAL: DATABASE_URL has no hostname. Scheme={parsed.scheme}')
        exit(1)
    print(f'DATABASE_URL OK: scheme={parsed.scheme}, host_len={len(parsed.hostname or \"\")}, path={parsed.path}')
else:
    print('WARNING: DATABASE_URL is empty — will fall back to individual DB_* vars')
" || { echo "=== DATABASE_URL validation failed — check Railway Variables tab ==="; exit 1; }

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
