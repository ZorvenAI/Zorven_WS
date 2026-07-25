#!/usr/bin/env bash
# Master deployment script — runs all steps in sequence.
# Usage:
#   ./deploy-all.sh              # Full deployment (steps 01-11)
#   ./deploy-all.sh --skip-infra # Skip infrastructure (steps 05-11 only)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

SKIP_INFRA=false
if [ "${1:-}" = "--skip-infra" ]; then
  SKIP_INFRA=true
fi

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Zorven Platform — GCP Cloud Run Deployment             ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# Check prerequisites
if ! command -v gcloud &>/dev/null; then
  echo "ERROR: gcloud CLI not found. Install: https://cloud.google.com/sdk/docs/install"
  exit 1
fi

if ! command -v docker &>/dev/null; then
  echo "ERROR: Docker not found. Install: https://docs.docker.com/get-docker/"
  exit 1
fi

# Check secrets.env exists
if [ ! -f "${SCRIPT_DIR}/secrets.env" ]; then
  echo "ERROR: secrets.env not found."
  echo "  Copy secrets.env.template to secrets.env and fill in values:"
  echo "  cp ${SCRIPT_DIR}/secrets.env.template ${SCRIPT_DIR}/secrets.env"
  exit 1
fi

START_TIME=$(date +%s)

run_step() {
  local script=$1
  local desc=$2
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  ${desc}"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  bash "${SCRIPT_DIR}/${script}"
}

if [ "${SKIP_INFRA}" = false ]; then
  run_step "01-setup-project.sh"            "Step 1/11: Project setup (APIs, IAM)"
  run_step "02-setup-networking.sh"         "Step 2/11: Networking (VPC, connector)"
  run_step "03-setup-redis.sh"              "Step 3/11: Redis (Cloud Memorystore)"
  run_step "04-setup-secrets.sh"            "Step 4/11: Secrets (Secret Manager)"
fi

run_step "05-setup-artifact-registry.sh"  "Step 5/11: Artifact Registry"
run_step "06-mirror-images.sh"            "Step 6/11: Mirror images (GHCR → AR)"
run_step "07-run-migrations.sh"           "Step 7/11: Database migrations"
run_step "08-deploy-services.sh"          "Step 8/11: Deploy services (first pass)"
run_step "09-collect-urls.sh"             "Step 9/11: Collect service URLs"
run_step "10-redeploy-with-urls.sh"       "Step 10/11: Redeploy with URLs (second pass)"
run_step "11-verify.sh"                   "Step 11/11: Health verification"

END_TIME=$(date +%s)
ELAPSED=$(( END_TIME - START_TIME ))
MINUTES=$(( ELAPSED / 60 ))
SECONDS=$(( ELAPSED % 60 ))

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  Deployment complete! (${MINUTES}m ${SECONDS}s)                        ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "Service URLs saved to: ${SCRIPT_DIR}/service-urls.env"
echo ""
echo "To tear down: ./99-teardown.sh"
echo "To redeploy (skip infra): ./deploy-all.sh --skip-infra"
