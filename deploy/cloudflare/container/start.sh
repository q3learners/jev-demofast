#!/bin/sh
# Headless Chromium for the tool to drive (debugging on 127.0.0.1 only), then the job server.
# Chrome runs as its own user with an empty environment, so a page that broke out of a renderer still couldn't read the
# API keys (they live in the job server's environment, owned by another user). The tool records in a background tab;
# headless Chromium throttles those unless told not to.
set -e
setpriv --reuid=chrome --regid=chrome --init-groups env -i HOME=/home/chrome PATH=/usr/bin:/bin \
  chromium --headless=new --no-sandbox --disable-dev-shm-usage --disable-gpu \
  --user-data-dir=/home/chrome/profile --remote-debugging-port=9333 --remote-debugging-address=127.0.0.1 \
  --disable-background-timer-throttling --disable-renderer-backgrounding --disable-backgrounding-occluded-windows \
  --no-first-run --no-default-browser-check --window-size=1440,900 about:blank >/tmp/chrome.log 2>&1 &
for _ in $(seq 1 50); do
  curl -sf http://127.0.0.1:9333/json/version >/dev/null && break
  sleep 0.2
done
exec setpriv --reuid=demo --regid=demo --init-groups env HOME=/home/demo python /app/server.py
