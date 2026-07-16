FROM python:3.12-slim

WORKDIR /app

# Install curl for container healthchecks
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

EXPOSE 8110

# Start script reads PROCESS_TYPE env var to select web/worker/beat
COPY start.sh .
RUN chmod +x start.sh
CMD ["./start.sh"]
