#!/bin/bash
# ==============================================================================
# US-001 Acceptance Criteria Verification
# Verifies MLflow Tracking Server is running and healthy in Docker Compose
#
# Usage: bash scripts/test_mlflow_health.sh
# Prerequisites: docker compose up mlflow-db mlflow-server -d
# ==============================================================================

set -e

MLFLOW_URL="${MLFLOW_URL:-http://localhost:5000}"
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

# AC-2: Backend store is PostgreSQL (verify MLflow API works, which requires DB)
echo "[AC-2] Backend store URI is PostgreSQL (API functional)..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "${MLFLOW_URL}/api/2.0/mlflow/experiments/search?max_results=1" 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
  check "MLflow API accessible (PostgreSQL backend store functional)" 0
else
  check "MLflow API returned ${HTTP_CODE} (expected 200)" 1
fi

# AC-3: Default artifact root is /mlflow/artifacts (verify via experiment)
echo "[AC-3] Artifact root configured at /mlflow/artifacts..."
ARTIFACT_CHECK=$(curl -s "${MLFLOW_URL}/api/2.0/mlflow/experiments/get?experiment_id=0" 2>/dev/null || echo "{}")
if echo "$ARTIFACT_CHECK" | grep -q "mlflow/artifacts"; then
  check "Artifact root contains /mlflow/artifacts" 0
else
  # Try creating a test experiment to verify
  CREATE_RESP=$(curl -s -X POST "${MLFLOW_URL}/api/2.0/mlflow/experiments/create" \
    -H "Content-Type: application/json" \
    -d '{"name": "__us001_artifact_verify__"}' 2>/dev/null || echo "{}")
  if echo "$CREATE_RESP" | grep -q "experiment_id"; then
    EXP_ID=$(echo "$CREATE_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['experiment_id'])" 2>/dev/null || echo "")
    GET_RESP=$(curl -s "${MLFLOW_URL}/api/2.0/mlflow/experiments/get?experiment_id=${EXP_ID}" 2>/dev/null || echo "{}")
    if echo "$GET_RESP" | grep -q "mlflow/artifacts"; then
      check "Artifact root verified via test experiment" 0
    else
      check "Artifact root not set to /mlflow/artifacts" 1
    fi
    # Cleanup test experiment
    curl -s -X POST "${MLFLOW_URL}/api/2.0/mlflow/experiments/delete" \
      -H "Content-Type: application/json" \
      -d "{\"experiment_id\": \"${EXP_ID}\"}" > /dev/null 2>&1 || true
  else
    check "Could not verify artifact root" 1
  fi
fi

# AC-4: Service joins app-network and depends on postgres healthy
echo "[AC-4] Network and dependency check..."
if command -v docker &> /dev/null; then
  NETWORK=$(docker inspect ai-brand-automator-mlflow --format='{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}' 2>/dev/null || echo "")
  if echo "$NETWORK" | grep -q "app-network\|deployment_app-network"; then
    check "MLflow joined app-network" 0
  else
    check "MLflow not on app-network (found: ${NETWORK:-none})" 1
  fi
else
  echo "  SKIP: Docker CLI not available for network check"
fi

# AC-5: Healthcheck runs every 30s with 3 retries and 10s timeout
echo "[AC-5] Healthcheck configuration..."
if command -v docker &> /dev/null; then
  HC_CONFIG=$(docker inspect ai-brand-automator-mlflow --format='Interval={{.Config.Healthcheck.Interval}} Timeout={{.Config.Healthcheck.Timeout}} Retries={{.Config.Healthcheck.Retries}}' 2>/dev/null || echo "")
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
