#!/usr/bin/env bash
# Jev drives a well-known open-source app from its source map, with no route plan.
# App: https://github.com/nextjs/saas-starter (MIT). Set it up per its README (Postgres + Stripe test key),
# run `pnpm db:migrate && pnpm db:seed && pnpm dev`, then:
#   examples/saas-starter-invite.sh ../saas-starter
set -euo pipefail
APP=${1:?path to your saas-starter clone}
: "${CLOUDFLARE_ACCOUNT_ID:?set it}" "${CLOUDFLARE_API_TOKEN:?set it}"
uv run jev-demofast index "$APP" --out out/saas-index.json
DEMO_PASSWORD=admin123 uv run jev-demofast demo \
  "Sign in as test@test.com with password {{PASSWORD}}, then invite jane@example.com to my team as a member." \
  --url http://localhost:3000/sign-in --index out/saas-index.json --fresh --gif --out out/saas-invite.mp4
