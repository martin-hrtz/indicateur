#!/usr/bin/env zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUNTIME_DIR="${PROJECT_DIR}/.runtime"
PIDS_FILE="${RUNTIME_DIR}/pids.json"

if [[ ! -f "${PIDS_FILE}" ]]; then
  echo "Aucun processus Confiance de Trade en cours."
  exit 0
fi

PYTHON_BIN="$(command -v python3 || true)"
if [[ -z "${PYTHON_BIN}" ]]; then
  echo "Python3 introuvable, arrêt impossible." >&2
  exit 1
fi

function read_pid() {
  local service="$1"
  "${PYTHON_BIN}" - "$service" "${PIDS_FILE}" <<'PY'
import json
import sys
service = sys.argv[1]
path = sys.argv[2]
with open(path, "r", encoding="utf-8") as fh:
    data = json.load(fh)
value = data.get(service) or {}
pid = value.get("pid")
print(pid or "")
PY
}

function stop_service() {
  local name="$1"
  local pid="$2"
  if [[ -z "$pid" ]]; then
    return
  fi
  if ! kill -0 "$pid" >/dev/null 2>&1; then
    return
  fi
  printf "[STOP] Extinction %s (pid %s)\n" "$name" "$pid"
  kill "$pid" >/dev/null 2>&1 || true
  for i in {1..10}; do
    if kill -0 "$pid" >/dev/null 2>&1; then
      sleep 0.5
    else
      break
    fi
  done
  if kill -0 "$pid" >/dev/null 2>&1; then
    printf "[STOP] Forçage %s (pid %s)\n" "$name" "$pid"
    kill -9 "$pid" >/dev/null 2>&1 || true
  fi
}

BACKEND_PID="$(read_pid backend)"
FRONTEND_PID="$(read_pid frontend)"

stop_service "backend" "$BACKEND_PID"
stop_service "frontend" "$FRONTEND_PID"

rm -f "${PIDS_FILE}"

echo "Arrêt OK"
