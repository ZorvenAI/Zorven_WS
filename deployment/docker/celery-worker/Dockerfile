# ==============================================================================
# Celery Worker Dockerfile
# Based on backend image with worker entrypoint
# ==============================================================================

# Stage 1: Builder (same as backend)
FROM python:3.12-slim as builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY ai-brand-automator/requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip && \
    pip install -r /tmp/requirements.txt && \
    pip install celery[redis] flower

# ==============================================================================
# Stage 2: Production Worker
FROM python:3.12-slim as production

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PATH="/opt/venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=brand_automator.settings \
    # Celery settings
    CELERY_BROKER_URL=redis://redis:6379/0 \
    CELERY_RESULT_BACKEND=redis://redis:6379/0

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash appuser

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

COPY ai-brand-automator/ /app/
COPY deployment/scripts/start-celery-worker.sh /app/start.sh
RUN chmod +x /app/start.sh

RUN mkdir -p /app/logs && chown -R appuser:appuser /app

USER appuser

# Health check - verify Celery worker is responding
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD celery -A brand_automator inspect ping -d celery@$HOSTNAME || exit 1

CMD ["/app/start.sh"]
