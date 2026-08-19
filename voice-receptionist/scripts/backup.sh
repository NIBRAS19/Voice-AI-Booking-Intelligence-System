#!/bin/bash
# Backup script for Voice Receptionist
# Usage: ./backup.sh

set -e

BACKUP_DIR="/backups/voice-receptionist"
DATE=$(date +%Y%m%d_%H%M%S)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "==================================="
echo "Voice Receptionist Backup"
echo "Date: $DATE"
echo "==================================="

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Backup PostgreSQL
echo "Backing up database..."
docker-compose -f "$PROJECT_DIR/docker-compose.prod.yml" exec -T postgres \
    pg_dump -U postgres voice_receptionist | gzip > "$BACKUP_DIR/db_$DATE.sql.gz"
echo "✓ Database backup created"

# Backup recordings (if any)
if [ -d "$PROJECT_DIR/recordings" ]; then
    echo "Backing up recordings..."
    tar -czf "$BACKUP_DIR/recordings_$DATE.tar.gz" -C "$PROJECT_DIR" recordings
    echo "✓ Recordings backup created"
fi

# Backup environment files
echo "Backing up configuration..."
tar -czf "$BACKUP_DIR/config_$DATE.tar.gz" -C "$PROJECT_DIR" \
    .env.production 2>/dev/null || true

# Cleanup old backups (keep last 7 days)
echo "Cleaning up old backups..."
find "$BACKUP_DIR" -name "*.gz" -mtime +7 -delete

# List backups
echo ""
echo "==================================="
echo "Backups in $BACKUP_DIR:"
ls -lh "$BACKUP_DIR"
echo "==================================="
