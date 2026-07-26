FROM python:3.12-slim
LABEL service="ad-publishing-agent-svc" port="8043"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config/ config/
COPY app/ app/

EXPOSE 8043

ENV PORT=8043

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD ["sh", "-c", "curl -f http://localhost:${PORT:-8043}/health || exit 1"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8043"]
