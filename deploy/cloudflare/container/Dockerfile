# The demo recorder for the hosted service: jev-demofast, headless Chromium, ffmpeg, and the job server.
# Built from the repository root: docker build -f deploy/cloudflare/container/Dockerfile .
FROM python:3.12-slim-bookworm

RUN apt-get update \
 && apt-get install -y --no-install-recommends chromium ffmpeg fonts-liberation fonts-dejavu-core \
      fonts-noto-color-emoji ca-certificates curl \
 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.9.18 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE NOTICE ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-cache
COPY deploy/cloudflare/container/server.py deploy/cloudflare/container/start.sh ./

RUN useradd --create-home demo && mkdir -p /data/runs && chown -R demo /data
USER demo
ENV PATH=/app/.venv/bin:$PATH \
    BU_CDP_URL=http://127.0.0.1:9333 \
    BH_TELEMETRY=0 BH_UPDATE_CHECK=0 \
    JDF_DATA=/data/runs PORT=8080
EXPOSE 8080
CMD ["/app/start.sh"]
