# Python base image
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Create logs and staticfiles directory
RUN mkdir -p logs staticfiles

# Expose port
EXPOSE 8000

# Create entrypoint script - v2 with production domains
RUN echo '#!/bin/bash\n\
set -e\n\
echo "=== Running migrations ==="\n\
python manage.py migrate --noinput\n\
echo "=== Setting up production domains ==="\n\
python add_production_domains.py\n\
echo "=== Collecting static files ==="\n\
python manage.py collectstatic --noinput --clear || true\n\
echo "=== Starting Gunicorn on port $PORT ==="\n\
exec gunicorn brand_automator.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --threads 2 --timeout 120 --access-logfile - --error-logfile -\n\
' > /app/entrypoint.sh && chmod +x /app/entrypoint.sh

# Run entrypoint
CMD ["/app/entrypoint.sh"]
