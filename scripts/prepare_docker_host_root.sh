#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DOCKER_ROOT="${PATCHWEAVER_DOCKER_ROOT:-/usr/local/patchweaver}"

mkdir -p \
  "${DOCKER_ROOT}/data" \
  "${DOCKER_ROOT}/workspaces" \
  "${DOCKER_ROOT}/docs/submission" \
  "${DOCKER_ROOT}/host/lib" \
  "${DOCKER_ROOT}/host/usr/src" \
  "${DOCKER_ROOT}/host/usr/lib" \
  "${DOCKER_ROOT}/host/usr/bin" \
  "${DOCKER_ROOT}/host/usr/libexec" \
  "${DOCKER_ROOT}/host/usr/share" \
  "${DOCKER_ROOT}/host/opt" \
  "${DOCKER_ROOT}/host/home/patchweaver"

sync_tree() {
  local source="$1"
  local target="$2"
  mkdir -p "$(dirname "${target}")"
  rm -rf "${target}"
  if command -v rsync >/dev/null 2>&1; then
    mkdir -p "${target}"
    rsync -a --delete "${source}/" "${target}/"
  else
    cp -a "${source}" "${target}"
  fi
}

link_path() {
  local source="$1"
  local target="$2"
  if [[ -e "${source}" ]]; then
    mkdir -p "$(dirname "${target}")"
    rm -rf "${target}"
    ln -s "${source}" "${target}"
  else
    printf 'warning: host path not found, skipped: %s\n' "${source}" >&2
  fi
}

sync_tree "${PROJECT_ROOT}/config" "${DOCKER_ROOT}/config"
sync_tree "${PROJECT_ROOT}/evaluations" "${DOCKER_ROOT}/evaluations"
if [[ -d "${PROJECT_ROOT}/docs/submission" ]]; then
  sync_tree "${PROJECT_ROOT}/docs/submission" "${DOCKER_ROOT}/docs/submission"
fi

link_path /lib/modules "${DOCKER_ROOT}/host/lib/modules"
link_path /usr/src/kernels "${DOCKER_ROOT}/host/usr/src/kernels"
link_path /usr/lib/debug "${DOCKER_ROOT}/host/usr/lib/debug"
link_path /opt/kernel-src "${DOCKER_ROOT}/host/opt/kernel-src"
link_path /home/patchweaver/kernel-src-prepared "${DOCKER_ROOT}/host/home/patchweaver/kernel-src-prepared"
link_path /usr/bin/kpatch-build "${DOCKER_ROOT}/host/usr/bin/kpatch-build"
link_path /usr/libexec/kpatch "${DOCKER_ROOT}/host/usr/libexec/kpatch"
link_path /usr/share/kpatch "${DOCKER_ROOT}/host/usr/share/kpatch"

printf 'PatchWeaver Docker host root prepared: %s\n' "${DOCKER_ROOT}"
