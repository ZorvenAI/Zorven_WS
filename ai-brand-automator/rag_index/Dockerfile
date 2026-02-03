# RAG Index Service Dockerfile
# Multi-stage build for optimized production image

# ============================================================================
# Stage 1: Builder
# ============================================================================
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install additional RAG index dependencies (versions pinned for security)
RUN pip install --no-cache-dir \
    google-cloud-storage==2.18.2 \
    google-cloud-aiplatform==1.79.0 \
    google-cloud-discoveryengine==0.13.5 \
    confluent-kafka==2.6.1 \
    redis[hiredis]==5.2.1


# ============================================================================
# Stage 2: Runtime
# ============================================================================
FROM python:3.12-slim AS runtime

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create non-root user
RUN groupadd -r ragindex && useradd -r -g ragindex ragindex

# Copy application code
COPY --chown=ragindex:ragindex . .

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_SETTINGS_MODULE=brand_automator.settings

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/rag-index/health/ || exit 1

# Switch to non-root user
USER ragindex

# Run the application
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
