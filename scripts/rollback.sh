#!/bin/bash

# Rollback script for TODO MCP Service
# Usage: ./scripts/rollback.sh [staging|production] [image_tag]

set -e

ENVIRONMENT=${1:-production}
IMAGE_TAG=${2:-latest}

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Rolling back ${ENVIRONMENT} environment to ${IMAGE_TAG}...${NC}"

if [ "$ENVIRONMENT" == "staging" ]; then
    COMPOSE_FILE="docker-compose.staging.yml"
    SERVICE_NAME="todo-mcp-service-staging"
    PORT=8005
elif [ "$ENVIRONMENT" == "production" ]; then
    COMPOSE_FILE="docker-compose.production.yml"
    SERVICE_NAME="todo-mcp-service-prod"
    PORT=8004
else
    echo -e "${RED}Invalid environment. Use 'staging' or 'production'${NC}"
    exit 1
fi

# Check if docker-compose file exists
if [ ! -f "$COMPOSE_FILE" ]; then
    echo -e "${RED}Error: $COMPOSE_FILE not found${NC}"
    exit 1
fi

# Create backup before rollback
echo -e "${YELLOW}Creating backup before rollback...${NC}"
docker exec ${SERVICE_NAME} python -c "
import sys
sys.path.insert(0, '/app')
from backup import BackupManager
import os
bm = BackupManager(os.getenv('TODO_BACKUPS_DIR', '/app/backups'))
backup_path = bm.create_backup()
print(f'Backup created: {backup_path}')
" || echo "Warning: Could not create backup"

# Stop current service
echo -e "${YELLOW}Stopping current service...${NC}"
docker-compose -f "$COMPOSE_FILE" down || true

# Pull previous image
echo -e "${YELLOW}Pulling previous image tag: ${IMAGE_TAG}...${NC}"
docker pull ghcr.io/${GITHUB_REPOSITORY:-your-repo/todo-mcp-service}:${IMAGE_TAG} || {
    echo -e "${YELLOW}Warning: Could not pull image. Proceeding with local rollback...${NC}"
}

# Update docker-compose with previous image tag
if [ -n "$IMAGE_TAG" ] && [ "$IMAGE_TAG" != "latest" ]; then
    export IMAGE_TAG="$IMAGE_TAG"
fi

# Start service with previous image
echo -e "${YELLOW}Starting service with previous image...${NC}"
docker-compose -f "$COMPOSE_FILE" up -d

# Wait for service to be healthy
echo -e "${YELLOW}Waiting for service to be healthy...${NC}"
MAX_RETRIES=30
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -f http://localhost:${PORT}/health > /dev/null 2>&1; then
        echo -e "${GREEN}Service is healthy after rollback${NC}"
        exit 0
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo -e "${YELLOW}Waiting for health check... (${RETRY_COUNT}/${MAX_RETRIES})${NC}"
    sleep 2
done

echo -e "${RED}Warning: Health check failed after rollback. Please verify manually.${NC}"
exit 1
