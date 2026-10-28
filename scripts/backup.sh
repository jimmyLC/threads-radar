#!/usr/bin/env bash
# SQLite 備份（選配，你選了只靠 VPS 快照；要用時掛進 cron 即可）
# crontab -e
#   0 9 * * * /opt/radar/scripts/backup.sh
set -euo pipefail

DB="${RADAR_DB:-/opt/radar/data/radar.db}"
OUT_DIR="${1:-/opt/radar/backup}"
KEEP_DAYS=7

mkdir -p "$OUT_DIR"
OUT="$OUT_DIR/radar-$(date +%F).db"
sqlite3 "$DB" ".backup '$OUT'"
find "$OUT_DIR" -name 'radar-*.db' -mtime +"$KEEP_DAYS" -delete
echo "backup -> $OUT"
