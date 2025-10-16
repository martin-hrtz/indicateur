#!/usr/bin/env zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_DIR="${PROJECT_DIR}/backend"
FRONTEND_DIR="${PROJECT_DIR}/frontend"
RUNTIME_DIR="${PROJECT_DIR}/.runtime"
LOG_DIR="${RUNTIME_DIR}/logs"

mkdir -p "${RUNTIME_DIR}" "${LOG_DIR}"

"${SCRIPT_DIR}/fix_perms.sh" >/dev/null 2>&1 || true

function log() {
  printf "[START] %s\n" "$1"
}

function fail() {
  printf "[START][ERREUR] %s\n" "$1" >&2
  exit 1
}

PYTHON_BIN="$(command -v python3 || true)"
if [[ -z "${PYTHON_BIN}" ]]; then
  fail "Python3 introuvable. Installez Python 3.10+"
fi

VENV_DIR="${BACKEND_DIR}/.venv"
if [[ ! -d "${VENV_DIR}" ]]; then
  log "Création de l'environnement virtuel"
  "${PYTHON_BIN}" -m venv "${VENV_DIR}" || fail "Impossible de créer le venv"
fi

"${VENV_DIR}/bin/pip" install --upgrade pip >/dev/null
log "Installation des dépendances backend"
"${VENV_DIR}/bin/pip" install -r "${BACKEND_DIR}/requirements.txt" >/dev/null

ENV_FILE="${BACKEND_DIR}/.env"
if [[ ! -f "${ENV_FILE}" ]]; then
  cat <<'ENVEOF' > "${ENV_FILE}"
TIMEZONE=Europe/Paris
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GOOGLE_API_KEY=
TWITTER_BEARER=
ENVEOF
  log "Fichier .env créé avec les valeurs par défaut"
fi

function port_free() {
  local port="$1"
  "${PYTHON_BIN}" - <<PY
import socket
import sys
port = int(sys.argv[1])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    try:
        s.bind(("127.0.0.1", port))
    except OSError:
        sys.exit(1)
sys.exit(0)
PY
  return $?
}

function choose_port() {
  local preferred="$1"
  local fallback="$2"
  if port_free "$preferred"; then
    echo "$preferred"
    return
  fi
  if port_free "$fallback"; then
    echo "$fallback"
    return
  fi
  local candidate=$(( fallback + 1 ))
  while true; do
    if port_free "$candidate"; then
      echo "$candidate"
      return
    fi
    candidate=$(( candidate + 1 ))
  done
}

BACKEND_PORT="$(choose_port 8000 8001)"
FRONTEND_PORT="$(choose_port 8080 8081)"

log "Lancement backend (port ${BACKEND_PORT})"
cd "${BACKEND_DIR}" || fail "Impossible d'accéder au backend"
nohup "${VENV_DIR}/bin/uvicorn" main:app --host 0.0.0.0 --port "${BACKEND_PORT}" \
  > "${LOG_DIR}/backend.log" 2>&1 &
BACKEND_PID=$!
cd - >/dev/null

log "Lancement frontend statique (port ${FRONTEND_PORT})"
cd "${FRONTEND_DIR}" || fail "Impossible d'accéder au frontend"
nohup "${PYTHON_BIN}" -m http.server "${FRONTEND_PORT}" --bind 127.0.0.1 \
  > "${LOG_DIR}/frontend.log" 2>&1 &
FRONTEND_PID=$!
cd - >/dev/null

cat <<PIDJSON > "${RUNTIME_DIR}/pids.json"
{
  "backend": {"pid": ${BACKEND_PID}, "port": ${BACKEND_PORT}},
  "frontend": {"pid": ${FRONTEND_PID}, "port": ${FRONTEND_PORT}}
}
PIDJSON

URL="http://localhost:${FRONTEND_PORT}"
log "Interface disponible sur ${URL}"
if command -v open >/dev/null 2>&1; then
  open "${URL}" >/dev/null 2>&1 || true
fi

echo "Démarrage Confiance de Trade OK"
