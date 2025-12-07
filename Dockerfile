# Telegram Streamer
# Multi-stage build for minimal image size

# ========================================
# Stage 1: Builder
# ========================================
FROM python:3.13-slim as builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir --upgrade pip wheel setuptools && \
    pip install --no-cache-dir .

# ========================================
# Stage 2: Runtime
# ========================================
FROM python:3.13-slim as runtime

LABEL maintainer="AetherVoyager"
LABEL description="Production-ready Telegram streaming app for video chats"
LABEL version="1.0.0"

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Install yt-dlp for YouTube support
RUN pip install --no-cache-dir yt-dlp

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application
COPY src/ src/

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash streamer && \
    mkdir -p /app/sessions && \
    chown -R streamer:streamer /app

USER streamer

# Session storage volume
VOLUME ["/app/sessions"]

# API port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8080/health').raise_for_status()"

# Environment variables with defaults
ENV TG_SESSION_PATH=/app/sessions \
    TG_SESSION_NAME=telegram_streamer \
    TG_API_HOST=0.0.0.0 \
    TG_API_PORT=8080 \
    TG_LOG_LEVEL=INFO \
    TG_LOG_JSON=true \
    TG_RECONNECT_ENABLED=true \
    TG_RECONNECT_MAX_ATTEMPTS=10 \
    TG_RECONNECT_TIMEOUT=90

# Default command - start API server
ENTRYPOINT ["tg-streamer"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8080", "--json-logs"]
