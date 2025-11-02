# Deployment Guide

This document describes the CI/CD pipeline and deployment procedures for the TODO MCP Service.

## CI/CD Pipeline Overview

The CI/CD pipeline is implemented using GitHub Actions and includes:

1. **Automated Testing** - Runs on every push and pull request
2. **Code Quality Checks** - Linting, formatting, type checking
3. **Security Scanning** - Dependency vulnerabilities and code security analysis
4. **Docker Image Building** - Builds and pushes container images
5. **Automated Deployments** - Staging and production deployments
6. **Rollback Capabilities** - Automatic rollback on deployment failure

## Pipeline Stages

### 1. Testing Stage (`test`)

- Runs all unit tests with pytest
- Generates code coverage reports
- Enforces minimum 80% coverage threshold
- Uploads coverage to Codecov

### 2. Code Quality Stage (`code-quality`)

Checks performed:
- **Black**: Code formatting
- **isort**: Import sorting
- **flake8**: Linting
- **pylint**: Code quality analysis
- **mypy**: Type checking

### 3. Security Scanning (`security`)

- **Safety**: Checks Python dependencies for known vulnerabilities
- **Bandit**: Security linter for Python code
- **Trivy**: Container image vulnerability scanning

### 4. Build Stage (`build`)

- Builds Docker image using Docker Buildx
- Pushes image to GitHub Container Registry (ghcr.io)
- Tags images with:
  - Branch name
  - Commit SHA
  - Semantic version (if tagged)
- Scans built image for vulnerabilities

### 5. Deployment Stages

#### Staging Deployment (`deploy-staging`)

- Triggers on pushes to `develop` branch
- Deploys to staging environment
- Runs smoke tests after deployment
- URL: `https://staging.example.com`

#### Production Deployment (`deploy-production`)

- Triggers on pushes to `main` branch (non-PR)
- Requires manual approval (configured in GitHub environment)
- Creates backup before deployment
- Deploys to production environment
- Runs comprehensive health checks
- URL: `https://production.example.com`

### 6. Rollback (`rollback`)

- Automatically triggers on deployment failure
- Restores previous version
- Verifies rollback success

## Deployment Environments

### Staging

- **Configuration**: `docker-compose.staging.yml`
- **Port**: 8005 (configurable via `STAGING_PORT`)
- **Database**: SQLite (default) or PostgreSQL
- **Log Level**: DEBUG
- **Purpose**: Pre-production testing

### Production

- **Configuration**: `docker-compose.production.yml`
- **Port**: 8004 (configurable via `PRODUCTION_PORT`)
- **Database**: PostgreSQL (recommended)
- **Log Level**: INFO
- **Purpose**: Live production service

## Manual Deployment

### Using GitHub Actions

1. Go to Actions ? Deploy workflow
2. Click "Run workflow"
3. Select environment (staging/production)
4. Optionally specify image tag (default: latest)
5. Click "Run workflow"

### Using Docker Compose

#### Staging

```bash
export STAGING_PORT=8005
export STAGING_DATA_DIR=./data/staging
docker-compose -f docker-compose.staging.yml up -d
```

#### Production

```bash
export PRODUCTION_PORT=8004
export PRODUCTION_DATA_DIR=./data/production
export POSTGRES_PASSWORD=your-secure-password
docker-compose -f docker-compose.production.yml up -d
```

## Rollback Procedures

### Automatic Rollback

The pipeline automatically rolls back on deployment failure:
- Detects deployment health check failures
- Restores previous container version
- Verifies rollback success

### Manual Rollback

#### Using Docker Compose

```bash
# Rollback staging
docker-compose -f docker-compose.staging.yml down
docker-compose -f docker-compose.staging.yml up -d

# Rollback production
docker-compose -f docker-compose.production.yml down
docker-compose -f docker-compose.production.yml up -d
```

#### Using Previous Docker Image

```bash
# Pull previous image tag
docker pull ghcr.io/your-repo/todo-mcp-service:previous-tag

# Update docker-compose.yml with previous tag
# Then redeploy
docker-compose -f docker-compose.production.yml up -d
```

## Environment Variables

### Staging

- `STAGING_PORT`: Service port (default: 8005)
- `STAGING_DATA_DIR`: Data directory path
- `STAGING_BACKUPS_DIR`: Backups directory path
- `LOG_LEVEL`: Logging level (default: DEBUG)

### Production

- `PRODUCTION_PORT`: Service port (default: 8004)
- `PRODUCTION_DATA_DIR`: Data directory path
- `PRODUCTION_BACKUPS_DIR`: Backups directory path
- `POSTGRES_PASSWORD`: PostgreSQL password (required)
- `POSTGRES_DB`: Database name (default: todos)
- `POSTGRES_USER`: Database user (default: postgres)
- `LOG_LEVEL`: Logging level (default: INFO)

## Health Checks

### Service Health Endpoint

```bash
# Check staging
curl http://localhost:8005/health

# Check production
curl http://localhost:8004/health
```

Expected response:
```json
{
  "status": "healthy",
  "database": "connected",
  "version": "1.0.0"
}
```

## Monitoring and Alerts

### GitHub Actions Status

- Check workflow runs in Actions tab
- Monitor deployment status
- Review test and security scan results

### Service Monitoring

- Health checks run every 30 seconds
- Failed health checks trigger alerts (if configured)
- Log aggregation for troubleshooting

## Best Practices

1. **Always test in staging first** before production deployment
2. **Review security scan results** before deploying
3. **Ensure test coverage** remains above 80%
4. **Use semantic versioning** for releases
5. **Monitor deployments** and verify health checks
6. **Keep backups** before production deployments
7. **Document changes** in commit messages

## Troubleshooting

### Deployment Fails

1. Check GitHub Actions logs for errors
2. Verify environment variables are set correctly
3. Ensure Docker and Docker Compose are installed
4. Check service logs: `docker logs todo-mcp-service-prod`

### Health Checks Fail

1. Verify service is running: `docker ps`
2. Check service logs for errors
3. Verify database connection
4. Check port conflicts

### Rollback Needed

1. Use manual rollback procedures above
2. Check previous image tags: `docker images`
3. Verify previous version health
4. Investigate issues before re-deploying
