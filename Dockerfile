# Multi-stage build using uv for reproducible, hash-locked installs.
FROM python:3.11-slim AS builder

RUN pip install --no-cache-dir uv==0.4.30
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev

FROM python:3.11-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        ffmpeg \
        curl \
    && rm -rf /var/lib/apt/lists/*
RUN pip install yt-dlp

# Install Node.js (for Claude Code CLI)
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*
RUN npm install -g @anthropic-ai/claude-code

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

COPY . /app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
