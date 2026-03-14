FROM python:3.12-slim AS base

WORKDIR /app

# Install system dependencies (curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# NOTE: spaCy model download removed to reduce container memory from ~742MiB
# to ~100MiB. Presidio PII detection falls back to regex patterns (same as APA).

# Copy application code
COPY . .

EXPOSE 8022

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8022"]
