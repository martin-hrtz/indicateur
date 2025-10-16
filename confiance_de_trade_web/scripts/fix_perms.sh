#!/usr/bin/env zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

function make_executable() {
  local path="$1"
  if [[ -e "$path" ]]; then
    chmod u+x "$path"
  fi
}

for target in "${PROJECT_DIR}"/*.command; do
  [[ -e "$target" ]] || continue
  make_executable "$target"
done

for script in "${PROJECT_DIR}/scripts"/*.sh; do
  [[ -e "$script" ]] || continue
  make_executable "$script"
done

if command -v xattr >/dev/null 2>&1; then
  xattr -dr com.apple.quarantine "${PROJECT_DIR}" 2>/dev/null || true
fi

echo "Permissions corrigées pour Confiance de Trade."
