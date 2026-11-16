#!/bin/sh
# POSIX shell restore script for Notification Service
# Usage: ./scripts/restore.sh <path-to-backup.sql.gz>

set -eu

if [ "$#" -lt 1 ]; then
    echo "Usage: $0 <backup-file.sql.gz>" >&2
    exit 1
fi

BACKUP_FILE="$1"

if [ ! -f "$BACKUP_FILE" ]; then
    echo "ERROR: Backup file '$BACKUP_FILE' does not exist." >&2
    exit 1
fi

POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-notification_db}"

printf "WARNING: This will replace the entire '%s' database with '%s'.\n" "$POSTGRES_DB" "$BACKUP_FILE"
printf "Type 'yes' to confirm and proceed: "
read -r CONFIRMATION

if [ "$CONFIRMATION" != "yes" ]; then
    echo "Restore cancelled by user."
    exit 1
fi

echo "Stopping application services (api and worker)..."
docker compose -f docker-compose.prod.yml stop api worker

echo "Recreating fresh database '${POSTGRES_DB}'..."
# Disconnect existing sessions and recreate database
docker compose -f docker-compose.prod.yml exec -T db psql -U "$POSTGRES_USER" -c "
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${POSTGRES_DB}' AND pid <> pg_backend_pid();
" >/dev/null 2>&1 || true

docker compose -f docker-compose.prod.yml exec -T db psql -U "$POSTGRES_USER" -c "DROP DATABASE IF EXISTS ${POSTGRES_DB};"
docker compose -f docker-compose.prod.yml exec -T db psql -U "$POSTGRES_USER" -c "CREATE DATABASE ${POSTGRES_DB};"

echo "Restoring data from ${BACKUP_FILE}..."
gunzip -c "$BACKUP_FILE" | docker compose -f docker-compose.prod.yml exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null

echo "Starting application services (api and worker)..."
docker compose -f docker-compose.prod.yml start api worker

echo "\nRestore completed successfully."
echo "Health Reminder:"
echo "  - Verify service status: docker compose -f docker-compose.prod.yml ps"
echo "  - Verify API health: curl -k https://localhost/health (or your domain)"
echo "  - Check application logs: docker compose -f docker-compose.prod.yml logs -f api"
