FROM ghcr.io/mlflow/mlflow:v2.21.0

# Install PostgreSQL driver for backend store
RUN pip install --no-cache-dir psycopg2-binary

EXPOSE 5000

# Shell form to allow environment variable expansion
CMD mlflow server \
    --host 0.0.0.0 \
    --port ${PORT:-5000} \
    --backend-store-uri "${MLFLOW_BACKEND_STORE_URI}" \
    --default-artifact-root "${MLFLOW_DEFAULT_ARTIFACT_ROOT:-/mlflow/artifacts}"
