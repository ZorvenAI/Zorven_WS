#!/bin/sh
# Starts celery beat + worker + uvicorn under tini.
# Traps SIGTERM/SIGINT and forwards to all children for clean shutdown.
set -e

PORT="${PORT:-8044}"

celery -A app.celery_app beat --loglevel=info &
BEAT_PID=$!

celery -A app.celery_app worker --loglevel=info --concurrency=4 &
WORKER_PID=$!

uvicorn app.main:app --host 0.0.0.0 --port "${PORT}" &
WEB_PID=$!

term() {
    echo "docker-entrypoint: caught signal, stopping children..."
    kill -TERM "$BEAT_PID" "$WORKER_PID" "$WEB_PID" 2>/dev/null || true
    wait "$BEAT_PID" "$WORKER_PID" "$WEB_PID" 2>/dev/null || true
    exit 0
}
trap term TERM INT

# Exit if any child exits
wait -n "$BEAT_PID" "$WORKER_PID" "$WEB_PID"
EXIT_CODE=$?
echo "docker-entrypoint: a child exited (code=$EXIT_CODE), shutting down..."
kill -TERM "$BEAT_PID" "$WORKER_PID" "$WEB_PID" 2>/dev/null || true
wait "$BEAT_PID" "$WORKER_PID" "$WEB_PID" 2>/dev/null || true
exit $EXIT_CODE
