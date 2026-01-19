# ==============================================================================
# Celery Beat Scheduler Dockerfile
# Periodic task scheduler
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
    pip install celery[redis]

# ==============================================================================
# Stage 2: Production Beat Scheduler
FROM python:3.12-slim as production

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PATH="/opt/venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=brand_automator.settings \
    CELERY_BROKER_URL=redis://redis:6379/0 \
    CELERY_RESULT_BACKEND=redis://redis:6379/0

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash appuser

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

COPY ai-brand-automator/ /app/
COPY deployment/scripts/start-celery-beat.sh /app/start.sh
RUN chmod +x /app/start.sh

# Create schedule database directory
RUN mkdir -p /app/logs /app/celerybeat && chown -R appuser:appuser /app

USER appuser

# No health check for beat - it's a scheduler, not a service

CMD ["/app/start.sh"]
