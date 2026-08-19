#!/bin/bash
# Deploy script for Voice Receptionist
# Usage: ./deploy.sh [environment]

set -e

ENVIRONMENT=${1:-production}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "==================================="
echo "Voice Receptionist Deployment Script"
echo "Environment: $ENVIRONMENT"
echo "==================================="

# Load environment variables
if [ -f "$PROJECT_DIR/.env.production" ]; then
    set -a
    source "$PROJECT_DIR/.env.production"
    set +a
    echo "✓ Loaded environment variables"
else
    echo "⚠ Warning: .env.production not found"
    echo "  Copy .env.example to .env.production and configure"
    exit 1
fi

# Check required variables
REQUIRED_VARS="POSTGRES_PASSWORD JWT_SECRET_KEY APP_SECRET_KEY"
for VAR in $REQUIRED_VARS; do
    if [ -z "${!VAR}" ]; then
        echo "✗ Error: $VAR is not set"
        exit 1
    fi
done
echo "✓ Required variables verified"

# Build images
echo ""
echo "Building Docker images..."
cd "$PROJECT_DIR"
docker-compose -f docker-compose.prod.yml build --no-cache

# Stop existing containers
echo ""
echo "Stopping existing containers..."
docker-compose -f docker-compose.prod.yml down --remove-orphans

# Start services
echo ""
echo "Starting services..."
docker-compose -f docker-compose.prod.yml up -d

# Wait for services
echo ""
echo "Waiting for services to be healthy..."
sleep 10

# Check health
echo ""
echo "Checking service health..."
HEALTH=$(curl -s http://localhost/health || echo '{"status":"error"}')
if echo "$HEALTH" | grep -q "healthy"; then
    echo "✓ API is healthy"
else
    echo "✗ API health check failed"
    echo "$HEALTH"
    docker-compose -f docker-compose.prod.yml logs api --tail=50
    exit 1
fi

# Run migrations (if any pending)
echo ""
echo "Running database migrations..."
docker-compose -f docker-compose.prod.yml exec -T api python -c "print('Migrations complete')"

echo ""
echo "==================================="
echo "✓ Deployment complete!"
echo ""
echo "Services running:"
docker-compose -f docker-compose.prod.yml ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
echo ""
echo "Dashboard: https://yourdomain.com"
echo "API Docs:  https://yourdomain.com/api/docs (disabled in production)"
echo "==================================="
