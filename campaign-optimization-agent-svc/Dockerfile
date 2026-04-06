FROM python:3.12-slim
LABEL service="campaign-optimization-agent-svc" port="8044"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/

EXPOSE 8044

ENV PORT=8044

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8044}/health || exit 1

# Start all 3 processes: celery beat, celery worker, and uvicorn
CMD celery -A app.celery_app beat -l info & \
    celery -A app.celery_app worker -l info & \
    uvicorn app.main:app --host 0.0.0.0 --port 8044
