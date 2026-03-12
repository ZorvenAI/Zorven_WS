FROM python:3.12-slim AS base

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install pinned spaCy model for Presidio PII detection (avoids download on first start)
ARG SPACY_MODEL_PACKAGE=en_core_web_lg==3.8.0
RUN pip install --no-cache-dir "$SPACY_MODEL_PACKAGE"

# Copy application code
COPY . .

EXPOSE 8021

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8021"]
