# Build the React application first. Its API base is deliberately relative so
# a browser always talks to the same host that served the UI (including Unraid).
# The output is static files, so build it once on the build machine's own
# platform rather than again under emulation for each target platform.
FROM --platform=$BUILDPLATFORM node:22-alpine AS ui-builder

WORKDIR /ui
COPY ui/package*.json ./
RUN npm install --no-audit --no-fund
COPY ui/ ./
RUN npm run build

# Resolve Python dependencies in an isolated virtual environment.
FROM python:3.12-slim AS api-builder

WORKDIR /build
ENV DEBIAN_FRONTEND=noninteractive
COPY --from=ghcr.io/astral-sh/uv:0.11.33 /uv /uvx /bin/
COPY api/ ./
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && uv sync --no-install-project --no-dev

# One runtime process serves both FastAPI and the compiled frontend.
FROM python:3.12-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY --from=denoland/deno:bin-2.9.5 /deno /usr/local/bin/deno
RUN chmod +x /usr/local/bin/deno

RUN groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -m appusr

RUN chown -R appusr:appgroup /root

WORKDIR /app


COPY --from=api-builder /build/.venv /app/.venv
COPY --from=api-builder /build/src /app/app
COPY --from=ui-builder /ui/dist /app/ui/dist

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python \
    ONTHESPOTDIR=/root/.config/onthespot \
    ONTHESPOTCACHEDIR=/root/.config/onthespot/cache \
    ONTHESPOT_WEBUI_DIST=/app/ui/dist \
    PATH=/app/.venv/bin:$PATH \
    HOME=/root

# The entrypoint makes the data folders writable as root, then runs CMD as
# PUID:PGID (default 1000:1000). See docker/entrypoint.sh.
COPY --chmod=755 docker/entrypoint.sh /usr/local/bin/entrypoint.sh

EXPOSE 6767 6768

# The image has no curl, so the healthcheck asks the API with Python. It
# skips any proxy, so HTTP_PROXY in the container cannot send it elsewhere.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD ["/app/.venv/bin/python", "-c", "import urllib.request; urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://127.0.0.1:6767/system/rate-limit', timeout=4)"]

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

CMD ["/app/.venv/bin/python", "-m", "uvicorn", "onthespot.main:app", "--app-dir", "/app/app", "--host", "0.0.0.0", "--port", "6767"]
