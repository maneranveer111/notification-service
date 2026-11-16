#!/bin/sh
# POSIX shell backup script for Notification Service
# Recommended cron job (daily at 03:00):
# 0 3 * * * cd /path/to/notification-service && ./scripts/backup.sh >> /var/log/notification-backup.log 2>&1
# Note: Always copy backups off-server (e.g. to S3, R2, or remote server) for disaster recovery.

set -eu

KEEP="${KEEP:-14}"
BACKUPS_DIR="backups"
mkdir -p "$BACKUPS_DIR"

POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-notification_db}"
TIMESTAMP=$(date +%Y-%m-%d-%H%M)
BACKUP_FILE="${BACKUPS_DIR}/notifications-${TIMESTAMP}.sql.gz"

echo "Creating database backup: ${BACKUP_FILE}..."

if ! docker compose -f docker-compose.prod.yml exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "$BACKUP_FILE"; then
    echo "ERROR: Backup failed." >&2
    rm -f "$BACKUP_FILE"
    exit 1
fi

if [ ! -s "$BACKUP_FILE" ]; then
    echo "ERROR: Backup file is empty." >&2
    rm -f "$BACKUP_FILE"
    exit 1
fi

echo "Backup created successfully: ${BACKUP_FILE}"

# Keep only the newest ${KEEP} backup files
TOTAL_FILES=$(ls -1t "${BACKUPS_DIR}"/notifications-*.sql.gz 2>/dev/null | wc -l)
if [ "$TOTAL_FILES" -gt "$KEEP" ]; then
    REMOVE_COUNT=$((TOTAL_FILES - KEEP))
    echo "Pruning ${REMOVE_COUNT} old backup(s) (retaining newest ${KEEP})..."
    ls -1t "${BACKUPS_DIR}"/notifications-*.sql.gz | tail -n "$REMOVE_COUNT" | xargs rm -f
fi
