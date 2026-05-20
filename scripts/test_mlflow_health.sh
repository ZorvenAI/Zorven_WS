#!/bin/bash
# ==============================================================================
# US-001 Acceptance Criteria Verification
# Verifies MLflow Tracking Server is running and healthy in Docker Compose
#
# Usage: bash scripts/test_mlflow_health.sh
# Prerequisites: docker compose up mlflow-db mlflow-server -d; curl; docker CLI
# ==============================================================================

set -e

MLFLOW_URL="${MLFLOW_URL:-http://localhost:5000}"
MLFLOW_CONTAINER="${MLFLOW_CONTAINER:-ai-brand-automator-mlflow}"
MLFLOW_DB_CONTAINER="${MLFLOW_DB_CONTAINER:-ai-brand-automator-mlflow-db}"
PASS=0
FAIL=0

check() {
  local label="$1"
  local result="$2"
  if [ "$result" = "0" ]; then
    echo "  PASS: $label"
    PASS=$((PASS + 1))
  else
    echo "  FAIL: $label"
    FAIL=$((FAIL + 1))
  fi
}

echo "=== US-001: MLflow Tracking Server Verification ==="
echo "Target: ${MLFLOW_URL}"
echo ""

# AC-1: MLflow server runs on port 5000 with health endpoint returning 200
echo "[AC-1] Health endpoint returns 200..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${MLFLOW_URL}/health" 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
  check "Health endpoint returned 200" 0
else
  check "Health endpoint returned ${HTTP_CODE} (expected 200)" 1
fi

# AC-2: Backend store URI uses PostgreSQL (verify via container env var)
echo "[AC-2] Backend store URI is PostgreSQL..."
if command -v docker &> /dev/null; then
  STORE_URI=$(docker inspect "${MLFLOW_CONTAINER}" --format='{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null | grep "^MLFLOW_BACKEND_STORE_URI=" | cut -d= -f2-)
  if echo "$STORE_URI" | grep -q "^postgresql://"; then
    check "Backend store URI is PostgreSQL: ${STORE_URI}" 0
  else
    check "Backend store URI is not PostgreSQL (found: ${STORE_URI:-not set})" 1
  fi
else
  # Fallback: verify API works (requires DB)
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${MLFLOW_URL}/api/2.0/mlflow/experiments/search?max_results=1" 2>/dev/null || echo "000")
  if [ "$HTTP_CODE" = "200" ]; then
    check "MLflow API accessible (DB backend functional, Docker CLI not available for URI check)" 0
  else
    check "MLflow API returned ${HTTP_CODE} (expected 200)" 1
  fi
fi

# AC-3: Default artifact root is /mlflow/artifacts (verify via default experiment)
echo "[AC-3] Artifact root configured at /mlflow/artifacts..."
ARTIFACT_CHECK=$(curl -s "${MLFLOW_URL}/api/2.0/mlflow/experiments/get?experiment_id=0" 2>/dev/null || echo "{}")
if echo "$ARTIFACT_CHECK" | grep -q "mlflow/artifacts"; then
  check "Default experiment artifact_location contains /mlflow/artifacts" 0
else
  # Fallback: check container env var
  if command -v docker &> /dev/null; then
    ART_ROOT=$(docker inspect "${MLFLOW_CONTAINER}" --format='{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null | grep "^MLFLOW_DEFAULT_ARTIFACT_ROOT=" | cut -d= -f2-)
    if [ "$ART_ROOT" = "/mlflow/artifacts" ]; then
      check "Artifact root env var set to /mlflow/artifacts" 0
    else
      check "Artifact root not set to /mlflow/artifacts (found: ${ART_ROOT:-not set})" 1
    fi
  else
    check "Could not verify artifact root (API returned unexpected data, Docker CLI not available)" 1
  fi
fi

# AC-4: Service joins app-network and depends on postgres healthy
echo "[AC-4] Network membership and dependency check..."
if command -v docker &> /dev/null; then
  # Check network membership
  NETWORK=$(docker inspect "${MLFLOW_CONTAINER}" --format='{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}' 2>/dev/null || echo "")
  if echo "$NETWORK" | grep -q "app-network\|deployment_app-network"; then
    check "MLflow joined app-network" 0
  else
    check "MLflow not on app-network (found: ${NETWORK:-none})" 1
  fi

  # Check depends_on: mlflow-db is healthy
  DB_HEALTH=$(docker inspect "${MLFLOW_DB_CONTAINER}" --format='{{.State.Health.Status}}' 2>/dev/null || echo "unknown")
  if [ "$DB_HEALTH" = "healthy" ]; then
    check "mlflow-db dependency is healthy" 0
  else
    check "mlflow-db health status: ${DB_HEALTH} (expected healthy)" 1
  fi
else
  echo "  SKIP: Docker CLI not available for network/dependency check"
fi

# AC-5: Healthcheck runs every 30s with 3 retries and 10s timeout
echo "[AC-5] Healthcheck configuration..."
if command -v docker &> /dev/null; then
  HC_CONFIG=$(docker inspect "${MLFLOW_CONTAINER}" --format='Interval={{.Config.Healthcheck.Interval}} Timeout={{.Config.Healthcheck.Timeout}} Retries={{.Config.Healthcheck.Retries}}' 2>/dev/null || echo "")
  if echo "$HC_CONFIG" | grep -q "Interval=30s" && echo "$HC_CONFIG" | grep -q "Timeout=10s" && echo "$HC_CONFIG" | grep -q "Retries=3"; then
    check "Healthcheck: interval=30s, timeout=10s, retries=3" 0
  else
    check "Healthcheck config mismatch (found: ${HC_CONFIG:-none})" 1
  fi
else
  echo "  SKIP: Docker CLI not available for healthcheck check"
fi

echo ""
echo "=== Results: ${PASS} passed, ${FAIL} failed ==="
if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
