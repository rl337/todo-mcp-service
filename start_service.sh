#!/bin/bash
# Startup script for todorama service
# Runs Alembic migrations before starting the service

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🔄 Running database migrations..."
# Run migrations using uv (same as service)
# Set DATABASE_PATH if needed (defaults to ./data/todos.db)
if [ -n "$DATABASE_PATH" ]; then
    export DATABASE_PATH
fi

# Try to run migrations - if alembic is not available, skip (for development)
if command -v uv &> /dev/null; then
    # Check if alembic is available in the project
    if uv run --help &> /dev/null; then
        # Try to run migrations - may fail if alembic not installed, that's OK
        uv run alembic upgrade head 2>/dev/null || echo "⚠️  Alembic migrations skipped (alembic may not be installed)"
    fi
else
    echo "⚠️  uv not found, skipping migrations"
fi

echo "🚀 Starting todorama service..."
# Start the service using the same command as before
exec uv run uvicorn todorama.main:app --host 0.0.0.0 --port 8004

