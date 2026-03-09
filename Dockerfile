# ─────────────────────────────────────────────────────────────────────────────
# Pesa AI Logger — Multi-stage Dockerfile
#
# Stage 1 (builder): install Python deps into a venv
# Stage 2 (runtime): copy only the venv + app code, run as non-root
#
# Build:  docker build -t pesa-logger .
# Run:    docker compose up          (recommended — uses docker-compose.yml)
#         docker run -p 5000:5000 --env-file .env pesa-logger
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: builder ─────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build deps (needed for some Python packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Create isolated venv
RUN python -m venv /build/venv
ENV PATH="/build/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt


# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Security: run as non-root user
RUN groupadd --gid 1001 pesa && \
    useradd  --uid 1001 --gid pesa --shell /bin/bash --create-home pesa

WORKDIR /app

# Copy venv from builder (no gcc needed at runtime)
COPY --from=builder /build/venv /app/venv
ENV PATH="/app/venv/bin:$PATH"

# Copy application source
COPY --chown=pesa:pesa . .

# Data directory for SQLite DB (mounted as volume in production)
RUN mkdir -p /app/data && chown pesa:pesa /app/data

# Drop to non-root
USER pesa

# Expose Flask default port
EXPOSE 5000

# Health check — polls /health every 30s
# Fails after 3 consecutive misses (90s) → container marked unhealthy
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')" \
    || exit 1

# Default: start the webhook server
# Override CMD in docker-compose or docker run for other subcommands
CMD ["python", "main.py", "serve", "--port", "5000"]