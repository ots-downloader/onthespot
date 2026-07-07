# Build stage
FROM python:3.12-slim AS builder

WORKDIR /app
#set non-interactive mode for apt-get
ENV DEBIAN_FRONTEND=noninteractive

# Install uv.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy source code
COPY . .

# Add necessary build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install project dependencies
RUN uv sync --frozen --no-install-project --no-dev

# Final stage
FROM python:3.12-slim AS runtime

WORKDIR /app

# Copy the virtual environment from the builder
COPY --from=builder /app/.venv /app/.venv
# Copy the application code
COPY ./src ./app/

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION="python" \
    PATH="/app/.venv/bin:$PATH"

# Expose port
EXPOSE 6767

CMD ["/app/.venv/bin/fastapi", "run", "/app/app/onthespot/main.py", "--port", "6767", "--host", "0.0.0.0"]
