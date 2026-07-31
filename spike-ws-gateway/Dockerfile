FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY echo/ echo/

EXPOSE 8120

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD ["sh", "-c", "curl -f http://localhost:${PORT:-8120}/health || exit 1"]

# Cloud Run injects PORT; locally it defaults to the OIA port from Design §4.2.
CMD ["sh", "-c", "uvicorn echo.main:app --host 0.0.0.0 --port ${PORT:-8120}"]
