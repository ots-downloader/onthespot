FROM python:3.12-slim as base

# Install uv.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

SHELL ["/bin/bash", "-c"]

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    libegl1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./app
COPY src ./app

WORKDIR /app

RUN uv sync --frozen --no-cache

CMD ["/app/.venv/bin/fastapi", "run", "app/src/onthespot/main.py", "--port", "6767", "--host", "0.0.0.0"]
