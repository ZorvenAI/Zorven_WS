#!/usr/bin/env bash
# Mirror all GHCR images to Artifact Registry.
# This pulls from GHCR and pushes to AR for Cloud Run to consume.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "${SCRIPT_DIR}/00-config.sh"

TOTAL=${#UNIQUE_IMAGES[@]}
COUNT=0
FAILED=0

log "Mirroring ${TOTAL} images from GHCR to Artifact Registry..."
log "  Source: ${GHCR_PREFIX}"
log "  Target: ${AR_PREFIX}"

for img in "${UNIQUE_IMAGES[@]}"; do
  COUNT=$((COUNT + 1))
  SRC="${GHCR_PREFIX}/${img}:latest"
  DST="${AR_PREFIX}/${img}:latest"

  log "  [${COUNT}/${TOTAL}] ${img}..."

  if docker pull "${SRC}" >/dev/null 2>&1; then
    docker tag "${SRC}" "${DST}"
    if docker push "${DST}" >/dev/null 2>&1; then
      log_ok "  [${COUNT}/${TOTAL}] ${img}"
    else
      log_err "  [${COUNT}/${TOTAL}] Failed to push ${img}"
      FAILED=$((FAILED + 1))
    fi
  else
    log_err "  [${COUNT}/${TOTAL}] Failed to pull ${img}"
    FAILED=$((FAILED + 1))
  fi
done

if [ "$FAILED" -gt 0 ]; then
  log_err "Mirror complete with ${FAILED} failures out of ${TOTAL} images."
  exit 1
else
  log_ok "All ${TOTAL} images mirrored successfully."
fi
