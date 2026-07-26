FROM python:3.12-slim
LABEL service="brand-architecture-agent-svc" port="8032"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config/ config/
COPY app/ app/

EXPOSE 8032

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD ["sh", "-c", "curl -f http://localhost:${PORT:-8032}/health || exit 1"]

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8032}"]
