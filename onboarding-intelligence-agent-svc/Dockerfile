FROM python:3.12-slim

WORKDIR /app

# Install curl for health checks
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m spacy download en_core_web_sm || echo "spaCy model download failed, PII will use regex fallback"

COPY config/ config/
COPY app/ app/

EXPOSE 8120

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD ["sh", "-c", "curl -f http://localhost:8120/health || exit 1"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8120"]
