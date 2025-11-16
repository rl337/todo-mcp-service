FROM python:3.11-alpine

# Install system dependencies
RUN apk add --no-cache \
    sqlite \
    gzip \
    curl \
    wget \
    && rm -rf /var/cache/apk/*

# Install UV
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Set working directory
WORKDIR /app

# Copy project files for dependency resolution
COPY pyproject.toml ./
COPY uv.lock* ./

# Copy application code (needed for uv sync to build the package)
COPY todorama/ ./todorama/

# Install dependencies using UV
# Use --frozen if uv.lock exists, otherwise install from pyproject.toml
RUN if [ -f uv.lock ]; then \
    uv sync --frozen --no-dev; \
    else \
    uv sync --no-dev; \
    fi

# Create data directory
RUN mkdir -p /app/data /app/backups && \
    chmod 755 /app/data /app/backups

# Non-root user for security (UID 1000 to match host user)
RUN adduser -D -u 1000 -s /bin/sh todo && \
    chown -R todo:todo /app

USER todo

# Expose HTTP port
EXPOSE 8004

# Health check (use GET instead of HEAD to avoid 405 Method Not Allowed)
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD wget -q -O- http://localhost:8004/health > /dev/null || exit 1

# Environment variables
ENV TODO_DB_PATH=/app/data/todos.db
ENV TODO_BACKUPS_DIR=/app/backups
ENV TODO_SERVICE_PORT=8004
ENV TODO_BACKUP_INTERVAL_HOURS=24

# Run the HTTP API server using UV (like other MCP services)
CMD ["uv", "run", "uvicorn", "todorama.main:app", "--host", "0.0.0.0", "--port", "8004"]
