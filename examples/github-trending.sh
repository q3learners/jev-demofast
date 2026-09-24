#!/usr/bin/env bash
# A public site, no index: an LLM plans once, Jev handles every judgment call. ~20-30 s.
set -euo pipefail
: "${CLOUDFLARE_ACCOUNT_ID:?set it}" "${CLOUDFLARE_API_TOKEN:?set it}"
uv run jev-demofast demo \
  "Show how to find hot trending open-source projects on GitHub this week, then open one and show which signals help you tell a genuine project from spam: stars, forks, recent commits, contributors, and README." \
  --url https://github.com/ --fresh --gif --out out/github-trending.mp4
