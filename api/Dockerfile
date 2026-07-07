# Build stage
FROM python:3.12-slim AS builder

# Install uv.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION="python" \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Install dependencies first to leverage Docker cache
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY pyproject.toml ./app/
RUN uv sync --frozen --no-install-project --no-dev

# Final stage
FROM python:3.12-slim AS runtime

WORKDIR /app

# Copy the virtual environment from the builder
COPY --from=builder /app/.venv /app/.venv

# Copy the application code
COPY src ./app/

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION="python" \
    PATH="/app/.venv/bin:$PATH"

# Expose port
EXPOSE 6767

CMD ["/app/.venv/bin/fastapi", "run", "/app/onthespot/main.py", "--port", "6767", "--host", "0.0.0.0"]
