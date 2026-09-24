#!/usr/bin/env bash
# A narrated demo behind a login. The password never reaches a model or a log: it's a {{PASSWORD}} placeholder.
# Usage: DEMO_PASSWORD='...' examples/narrated-login.sh https://staging.example.com test@example.com "Acme, a ..."
set -euo pipefail
URL=${1:?staging URL}; EMAIL=${2:?test account}; PRODUCT=${3:-}
: "${DEMO_PASSWORD:?set DEMO_PASSWORD}"
uv run jev-demofast demo "Log in with email $EMAIL and password {{PASSWORD}}, go to the dashboard, and show what's there." \
  --url "$URL" --fresh --voice apollo --product "$PRODUCT" --out out/narrated-login.mp4
