#!/usr/bin/env bash
#
# One-time: allow the browser to PUT audio into the landing bucket (F-03).
#
# Meeting audio is uploaded by the browser directly to a GCS resumable session
# that Django mints — NFR-REL-01 puts the buffer on the client ("the client
# buffers locally and resumes upload"), so the bytes never pass through our
# servers. A cross-origin PUT needs the bucket to say so, and GCS bucket CORS
# is not something an application can set per request.
#
# Without this the upload fails **only in a browser**, with an opaque CORS
# error, while working perfectly from curl and from every test that is not a
# real browser. That asymmetry is the reason this file exists rather than a
# line in a runbook.
#
# Not part of deploy-all.sh: it configures a bucket the numbered scripts do not
# create (zorven-raw-assets predates them), and it only needs running when the
# bucket or the frontend origins change.
#
# Usage:
#   ./12-bucket-cors.sh                  # apply
#   ./12-bucket-cors.sh --show           # print the bucket's current policy

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/00-config.sh"

BUCKET="${GS_BUCKET_NAME:-zorven-raw-assets}"

if [[ "${1:-}" == "--show" ]]; then
  gcloud storage buckets describe "gs://${BUCKET}" --format="value(cors_config)"
  exit 0
fi

CORS_FILE="$(mktemp)"
trap 'rm -f "${CORS_FILE}"' EXIT

# `Content-Range` is the one that matters and the one most often missed: a
# resumable PUT carries it on every chunk, and a bucket that does not list it
# in responseHeader rejects the preflight.
cat >"${CORS_FILE}" <<'JSON'
[
  {
    "origin": [
      "https://zorven.ai",
      "https://www.zorven.ai",
      "http://localhost:3000"
    ],
    "method": ["PUT", "POST", "GET", "HEAD"],
    "responseHeader": [
      "Content-Type",
      "Content-Range",
      "Range",
      "x-goog-resumable"
    ],
    "maxAgeSeconds": 3600
  }
]
JSON

echo "Applying CORS to gs://${BUCKET}…"
gcloud storage buckets update "gs://${BUCKET}" --cors-file="${CORS_FILE}"
echo "Done. Verify with: $0 --show"
