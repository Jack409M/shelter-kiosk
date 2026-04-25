#!/usr/bin/env bash
set -euo pipefail

: "${SOURCE_DATABASE_URL:?SOURCE_DATABASE_URL is required and must point to the source Postgres database}"

BACKUP_DIR="${BACKUP_DIR:-./backups/postgres}"
BACKUP_PREFIX="${BACKUP_PREFIX:-shelter-kiosk}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUTPUT_FILE="${BACKUP_DIR}/${BACKUP_PREFIX}-${TIMESTAMP}.sql.gz"
LATEST_FILE="${BACKUP_DIR}/${BACKUP_PREFIX}-latest.sql.gz"

case "${SOURCE_DATABASE_URL}" in
  postgres://*|postgresql://*)
    ;;
  *)
    echo "ERROR: SOURCE_DATABASE_URL must be a Postgres URL." >&2
    exit 1
    ;;
esac

mkdir -p "${BACKUP_DIR}"

echo "[backup] exporting Postgres backup"
echo "[backup] destination: ${OUTPUT_FILE}"

pg_dump \
  --no-owner \
  --no-privileges \
  --format=plain \
  "${SOURCE_DATABASE_URL}" \
  | gzip > "${OUTPUT_FILE}"

test -s "${OUTPUT_FILE}"

cp "${OUTPUT_FILE}" "${LATEST_FILE}"

sha256sum "${OUTPUT_FILE}" > "${OUTPUT_FILE}.sha256"
sha256sum "${LATEST_FILE}" > "${LATEST_FILE}.sha256"

echo "[backup] complete"
echo "[backup] file: ${OUTPUT_FILE}"
echo "[backup] latest: ${LATEST_FILE}"
echo "[backup] sha256: ${OUTPUT_FILE}.sha256"
