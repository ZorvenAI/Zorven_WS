#!/bin/bash
# ==============================================================================
# Health Check Script
# Checks if services are healthy
# ==============================================================================

set -e

check_backend() {
    curl -sf http://localhost:${PORT:-8000}/health/ > /dev/null 2>&1
}

check_redis() {
    python << END
import redis
import os
redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
r = redis.from_url(redis_url)
r.ping()
END
}

check_database() {
    python << END
import psycopg2
import os
from urllib.parse import urlparse

database_url = os.environ.get("DATABASE_URL")
if database_url:
    parsed = urlparse(database_url)
    conn = psycopg2.connect(
        host=parsed.hostname,
        port=parsed.port or 5432,
        user=parsed.username,
        password=parsed.password,
        dbname=parsed.path[1:]
    )
    conn.close()
END
}

case "$1" in
    backend)
        check_backend && echo "Backend: OK" || (echo "Backend: FAILED" && exit 1)
        ;;
    redis)
        check_redis && echo "Redis: OK" || (echo "Redis: FAILED" && exit 1)
        ;;
    database)
        check_database && echo "Database: OK" || (echo "Database: FAILED" && exit 1)
        ;;
    all)
        check_backend && echo "Backend: OK" || echo "Backend: FAILED"
        check_redis && echo "Redis: OK" || echo "Redis: FAILED"
        check_database && echo "Database: OK" || echo "Database: FAILED"
        ;;
    *)
        echo "Usage: $0 {backend|redis|database|all}"
        exit 1
        ;;
esac
