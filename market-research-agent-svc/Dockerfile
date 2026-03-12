FROM python:3.12-slim AS base

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download spaCy model for Presidio PII detection (avoids 400MB download on first start)
RUN python -m spacy download en_core_web_lg

# Copy application code
COPY . .

EXPOSE 8021

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8021"]
