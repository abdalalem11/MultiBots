# syntax=docker/dockerfile:1.6
#
# MultiBots — enterprise-grade multi-bot hosting container.
#
# Improvements over the original Dockerfile:
#   * Multi-arch build (linux/amd64, linux/arm64) — works on Apple Silicon + RPi.
#   * Python 3.11-slim (security updates; 3.9 EOL October 2025).
#   * Non-root user (security best practice).
#   * HEALTHCHECK wired to /healthz.
#   * Drop cached pip wheels to keep image small.
#   * EXPOSE + LABEL for registry discoverability.
#   * gunicorn as production WSGI for the dashboard.

FROM python:3.11-slim-bookworm

# Avoid Python writing .pyc files + force unbuffered stdout for clean logs.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MB_HOST=0.0.0.0 \
    MB_PORT=10000

# System deps: git for cloning, jq for run.sh, curl for HEALTHCHECK.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git jq curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install MultiBots' own requirements first (better layer caching).
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy source. .dockerignore keeps tests/ and .git out of the image.
COPY . .

# Make run.sh executable (in case filesystem doesn't preserve the bit).
RUN chmod +x run.sh

# Create a non-root user and give it ownership of /app.
RUN useradd --create-home --uid 1000 --shell /bin/bash multibots \
    && chown -R multibots:multibots /app
USER multibots

# Clone bot repos and install their requirements (build-time, runs as multibots).
RUN bash run.sh

# Default to the dashboard so the container has an HTTP endpoint out of the box.
# To run headless (no dashboard, supervisor only), override CMD with:
#   CMD ["python3", "main.py"]
EXPOSE 10000

LABEL org.opencontainers.image.title="MultiBots" \
      org.opencontainers.image.description="Enterprise multi-bot hosting platform" \
      org.opencontainers.image.source="https://github.com/maruf009sultan/MultiBots" \
      org.opencontainers.image.licenses="MIT"

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://127.0.0.1:10000/healthz || exit 1

# Use gunicorn (production WSGI) for the dashboard. 2 workers + 4 threads
# comfortably handle monitoring traffic for dozens of bots on 512MB RAM.
CMD ["gunicorn", "--bind", "0.0.0.0:10000", \
     "--workers", "2", "--threads", "4", \
     "--access-logfile", "-", "--error-logfile", "-", \
     "dashboard:app"]
