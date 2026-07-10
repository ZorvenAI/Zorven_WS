#!/usr/bin/env bash
# seed_and_promote_prompts.sh — Seed all prompts into MLflow and promote to PRODUCTION.
#
# Usage:
#   ./scripts/seed_and_promote_prompts.sh                          # default: http://localhost:8110
#   ./scripts/seed_and_promote_prompts.sh https://poi.railway.app  # Railway URL
#
# The lifecycle requires: DRAFT → STAGING → CANARY → PRODUCTION (3 transitions per prompt).
# Auth: X-User-Role: admin header (RBAC allows ADMIN to promote).

set -euo pipefail

BASE_URL="${1:-http://localhost:8110}"
ROLE_HEADER="X-User-Role: admin"
CONTENT_TYPE="Content-Type: application/json"

# All 39 prompts from prompt_catalog.py
PROMPTS=(
  # WF1 — Brand Discovery (23)
  "zorven-wf1-mra-planning"
  "zorven-wf1-mra-synthesis"
  "zorven-wf1-mra-skill-synthesis"
  "zorven-wf1-mra-skill-report"
  "zorven-wf1-cia-planning"
  "zorven-wf1-cia-synthesis"
  "zorven-wf1-cia-swot"
  "zorven-wf1-cia-positioning-gap"
  "zorven-wf1-cia-benchmarking"
  "zorven-wf1-apa-planning"
  "zorven-wf1-apa-synthesis"
  "zorven-wf1-apa-demographic"
  "zorven-wf1-apa-psychographic"
  "zorven-wf1-apa-persona-synthesis"
  "zorven-wf1-apa-journey"
  "zorven-wf1-tcia-scoring"
  "zorven-wf1-tcia-persona-mapping"
  "zorven-wf1-tcia-report-synthesis"
  "zorven-wf1-voca-synthesis"
  "zorven-wf1-voca-sentiment-analysis"
  "zorven-wf1-voca-theme-clustering"
  "zorven-wf1-voca-nps-analysis"
  "zorven-wf1-voca-strategy-bridge"
  # WF2 — Brand Strategy (7)
  "zorven-wf2-bpa-positioning"
  "zorven-wf2-baa-hierarchy"
  "zorven-wf2-bpv-personality"
  "zorven-wf2-nta-naming"
  "zorven-wf2-nta-tagline"
  "zorven-wf2-bsa-origin"
  "zorven-wf2-bsa-narrative"
  # WF3 — Campaign Activation (9)
  "zorven-wf3-caa-blueprint"
  "zorven-wf3-caa-blueprint-synthesis"
  "zorven-wf3-cga-creative-director"
  "zorven-wf3-cga-copywriting"
  "zorven-wf3-cga-compliance"
  "zorven-wf3-adpub-publishing"
  "zorven-wf3-coa-recommendation"
  "zorven-wf3-coa-reporter"
  "zorven-wf3-ila-extraction"
)

echo "=========================================="
echo "Prompt Optimization — Seed & Promote"
echo "=========================================="
echo "Target: $BASE_URL"
echo "Prompts: ${#PROMPTS[@]}"
echo ""

# ── Step 1: Seed all prompts into MLflow (creates as DRAFT) ──────
echo "▶ Step 1: Seeding prompt catalog into MLflow..."
SEED_RESPONSE=$(curl -sf -X POST "$BASE_URL/v1/prompts/seed" \
  -H "$CONTENT_TYPE" 2>&1) || {
  echo "✗ Seed request failed. Is prompt-optimization-svc running at $BASE_URL?"
  echo "  Response: $SEED_RESPONSE"
  exit 1
}
echo "  $SEED_RESPONSE"
echo ""

# ── Step 2: Promote each prompt through DRAFT → STAGING → CANARY → PRODUCTION ──
SUCCEEDED=0
FAILED=0
SKIPPED=0

promote() {
  local name="$1"
  local version="$2"
  local target_state="$3"

  local resp
  resp=$(curl -sf -X PUT "$BASE_URL/v1/prompts/$name/versions/$version/promote" \
    -H "$CONTENT_TYPE" \
    -H "$ROLE_HEADER" \
    -d "{\"target_state\": \"$target_state\"}" 2>&1) || true

  # Check for success in response
  if echo "$resp" | grep -q '"success":true\|"success": true'; then
    return 0
  else
    echo "    ⚠ $name → $target_state: $resp"
    return 1
  fi
}

echo "▶ Step 2: Promoting all prompts to PRODUCTION..."
echo "  (DRAFT → STAGING → CANARY → PRODUCTION, 3 transitions each)"
echo ""

for name in "${PROMPTS[@]}"; do
  printf "  %-45s " "$name"

  # Transition 1: DRAFT → STAGING
  if ! promote "$name" 1 "STAGING"; then
    echo "[FAILED at STAGING]"
    FAILED=$((FAILED + 1))
    continue
  fi

  # Transition 2: STAGING → CANARY
  if ! promote "$name" 1 "CANARY"; then
    echo "[FAILED at CANARY]"
    FAILED=$((FAILED + 1))
    continue
  fi

  # Transition 3: CANARY → PRODUCTION
  if ! promote "$name" 1 "PRODUCTION"; then
    echo "[FAILED at PRODUCTION]"
    FAILED=$((FAILED + 1))
    continue
  fi

  echo "[✓ PRODUCTION]"
  SUCCEEDED=$((SUCCEEDED + 1))
done

echo ""
echo "=========================================="
echo "Results"
echo "=========================================="
echo "  Succeeded: $SUCCEEDED"
echo "  Failed:    $FAILED"
echo "  Total:     ${#PROMPTS[@]}"
echo ""

if [ "$FAILED" -gt 0 ]; then
  echo "⚠ Some prompts failed to promote. Check the output above for details."
  echo "  Failed prompts will continue using hardcoded fallback prompts."
  exit 1
else
  echo "✓ All ${#PROMPTS[@]} prompts are now in PRODUCTION state."
  echo "  Agents with PROMPT_FALLBACK_ONLY=False will load these from MLflow."
fi
