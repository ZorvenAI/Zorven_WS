FROM python:3.12-slim

WORKDIR /app

# Install Python dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

EXPOSE 8110

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8110"]
