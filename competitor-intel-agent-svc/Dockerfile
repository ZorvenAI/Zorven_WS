FROM python:3.12-slim AS base

WORKDIR /app

# Install system dependencies (curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install spaCy model for Presidio PII detection (optional — falls back to regex)
RUN python -m spacy download en_core_web_sm || echo "spaCy model download failed — Presidio will use regex fallback"

# Copy application code
COPY . .

EXPOSE 8022

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8022"]
