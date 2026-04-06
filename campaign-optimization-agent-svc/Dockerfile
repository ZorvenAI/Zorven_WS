FROM python:3.12-slim
LABEL service="campaign-optimization-agent-svc" port="8044"

WORKDIR /app

# tini = minimal init for proper signal forwarding + zombie reaping when
# we run multiple child processes (celery beat + worker + uvicorn).
RUN apt-get update && apt-get install -y --no-install-recommends curl tini && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8044

ENV PORT=8044

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8044}/health || exit 1

# tini as PID 1 → forwards SIGTERM to entrypoint → entrypoint traps and
# kills all child processes cleanly.
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/usr/local/bin/docker-entrypoint.sh"]
