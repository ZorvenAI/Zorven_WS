#!/bin/bash
# Starts celery beat + worker + uvicorn under tini.
# Traps SIGTERM/SIGINT and forwards to all children for clean shutdown.
PORT="${PORT:-8044}"

# Start celery beat + worker in the background. We deliberately do NOT
# fail the container if these crash — the healthcheck only cares about
# the FastAPI port, and we want the API to stay up even if Celery has
# issues (e.g., broker unavailable on first boot).
celery -A app.celery_app beat --loglevel=info &
BEAT_PID=$!

celery -A app.celery_app worker --loglevel=info --concurrency=4 &
WORKER_PID=$!

term() {
    echo "docker-entrypoint: caught signal, stopping children..."
    kill -TERM "$BEAT_PID" "$WORKER_PID" "$WEB_PID" 2>/dev/null || true
    wait 2>/dev/null || true
    exit 0
}
trap term TERM INT

# Foreground: uvicorn — its lifetime governs the container.
uvicorn app.main:app --host 0.0.0.0 --port "${PORT}" &
WEB_PID=$!
wait "$WEB_PID"
EXIT_CODE=$?
kill -TERM "$BEAT_PID" "$WORKER_PID" 2>/dev/null || true
exit $EXIT_CODE
