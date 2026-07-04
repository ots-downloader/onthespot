FROM python:3.12-slim AS base

# Install uv.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION="python" \
    PATH="/app/.venv/bin:$PATH"

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    ca-certificates \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./app/
COPY src ./app/

WORKDIR /app

RUN uv sync --no-cache

CMD ["/app/.venv/bin/fastapi", "run", "/app/onthespot/main.py", "--port", "6767", "--host", "0.0.0.0"]
