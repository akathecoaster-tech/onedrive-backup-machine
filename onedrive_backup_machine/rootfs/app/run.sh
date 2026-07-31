#!/bin/sh
set -eu

DATA_DIR="${ODBM_DATA_DIR:-/data}"
OPTIONS_FILE="/data/options.json"

if [ -f "$OPTIONS_FILE" ]; then
  # Prefer jq when available; fall back to python for local/dev runs.
  if command -v jq >/dev/null 2>&1; then
    export ODBM_CLIENT_ID="${ODBM_CLIENT_ID:-$(jq -r '.client_id // empty' "$OPTIONS_FILE")}"
    export ODBM_BACKUP_ROOT="${ODBM_BACKUP_ROOT:-$(jq -r '.backup_root // "/share/onedrive_backup_machine"' "$OPTIONS_FILE")}"
    export ODBM_LISTEN_PORT="${ODBM_LISTEN_PORT:-$(jq -r '.listen_port // 8080' "$OPTIONS_FILE")}"
  else
    eval "$(python3 - <<'PY'
import json, shlex
from pathlib import Path
opts = json.loads(Path("/data/options.json").read_text())
print("export ODBM_CLIENT_ID=" + shlex.quote(str(opts.get("client_id") or "")))
print("export ODBM_BACKUP_ROOT=" + shlex.quote(str(opts.get("backup_root") or "/share/onedrive_backup_machine")))
print("export ODBM_LISTEN_PORT=" + shlex.quote(str(opts.get("listen_port") or 8080)))
PY
)"
  fi
fi

export ODBM_CLIENT_ID="${ODBM_CLIENT_ID:-}"
export ODBM_BACKUP_ROOT="${ODBM_BACKUP_ROOT:-/share/onedrive_backup_machine}"
export ODBM_LISTEN_PORT="${ODBM_LISTEN_PORT:-8080}"
export ODBM_DATA_DIR="$DATA_DIR"

mkdir -p "$DATA_DIR" "$ODBM_BACKUP_ROOT"
exec python3 /app/main.py
