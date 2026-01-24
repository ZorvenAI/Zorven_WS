#!/bin/bash
# Kong Docker Entrypoint Script
# Processes environment variables in kong.yaml before starting Kong

set -e

echo "=== Kong Entrypoint: Processing environment variables ==="

# Create writable directory for processed config
mkdir -p /tmp/kong/declarative

# Substitute environment variables in the kong.yaml template
envsubst '${JWT_SECRET_KEY} ${CORS_ALLOWED_ORIGINS} ${GCP_ACCESS_TOKEN}' \
    < /usr/local/kong/declarative/kong.yaml.template \
    > /tmp/kong/declarative/kong.yaml

# Point Kong to the processed config
export KONG_DECLARATIVE_CONFIG=/tmp/kong/declarative/kong.yaml

# Verify the substitution worked (mask secret in output)
JWT_MASKED=$(echo "${JWT_SECRET_KEY:-not-set}" | head -c 8)
echo "  JWT_SECRET_KEY: ${JWT_MASKED}..."
echo "  CORS_ALLOWED_ORIGINS: ${CORS_ALLOWED_ORIGINS:-not-set}"
echo "  Config written to /tmp/kong/declarative/kong.yaml"

# Execute Kong's original entrypoint
echo "=== Starting Kong ==="
exec /docker-entrypoint-original.sh "$@"
