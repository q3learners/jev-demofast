#!/usr/bin/env bash
# Your own Next.js app: build the index from source, then Jev drives with no route plan.
# Usage: examples/nextjs-password-reset.sh ../my-nextjs-app https://staging.example.com test@example.com
set -euo pipefail
REPO=${1:?path to your Next.js repo}; URL=${2:?staging URL}; EMAIL=${3:?a test account email}
: "${CLOUDFLARE_ACCOUNT_ID:?set it}" "${CLOUDFLARE_API_TOKEN:?set it}"
uv run jev-demofast index "$REPO" --out out/app-index.json
uv run jev-demofast demo "Reset my password for the user $EMAIL" \
  --url "$URL" --index out/app-index.json --fresh --out out/password-reset.mp4
