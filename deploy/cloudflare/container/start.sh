#!/bin/sh
# Headless Chromium for the tool to drive (debugging on 127.0.0.1 only), then the job server. The tool records in a
# background tab; headless Chromium throttles those (menus didn't open on hover, screenshots timed out) unless told not to.
set -e
chromium --headless=new --no-sandbox --disable-dev-shm-usage --disable-gpu \
  --user-data-dir=/tmp/chrome-profile --remote-debugging-port=9333 --remote-debugging-address=127.0.0.1 \
  --disable-background-timer-throttling --disable-renderer-backgrounding --disable-backgrounding-occluded-windows \
  --no-first-run --no-default-browser-check --window-size=1440,900 about:blank >/tmp/chrome.log 2>&1 &
for _ in $(seq 1 50); do
  curl -sf http://127.0.0.1:9333/json/version >/dev/null && break
  sleep 0.2
done
exec python /app/server.py
