# Build the React application first. Its API base is deliberately relative so
# a browser always talks to the same host that served the UI (including Unraid).
FROM node:22-alpine AS ui-builder

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


RUN groupadd -g 1001 appgroup && \
    useradd -u 1001 -g appgroup -m otsusr

USER otsusr

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

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
    PATH=/app/.venv/bin:$PATH

EXPOSE 6767 6768


CMD ["/app/.venv/bin/python", "-m", "uvicorn", "onthespot.main:app", "--app-dir", "/app/app", "--host", "0.0.0.0", "--port", "6767"]
