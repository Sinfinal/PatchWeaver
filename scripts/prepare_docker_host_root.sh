#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DOCKER_ROOT="${PATCHWEAVER_DOCKER_ROOT:-/usr/local/patchweaver}"
HOST_PYTHON_BIN=""

select_host_python() {
  local candidate=""
  local candidates=()
  if [[ -n "${PATCHWEAVER_HOST_PYTHON:-}" ]]; then
    candidates+=("${PATCHWEAVER_HOST_PYTHON}")
  fi
  candidates+=(python3 python /usr/bin/python3 /usr/bin/python)

  for candidate in "${candidates[@]}"; do
    if ! command -v "${candidate}" >/dev/null 2>&1 && [[ ! -x "${candidate}" ]]; then
      continue
    fi
    if "${candidate}" - <<'PY' >/dev/null 2>&1
import yaml
PY
    then
      HOST_PYTHON_BIN="${candidate}"
      return 0
    fi
  done

  echo "missing host python with PyYAML support; set PATCHWEAVER_HOST_PYTHON to a usable interpreter" >&2
  return 1
}

select_host_python

mkdir -p \
  "${DOCKER_ROOT}/data" \
  "${DOCKER_ROOT}/workspaces" \
  "${DOCKER_ROOT}/docs/submission" \
  "${DOCKER_ROOT}/stable" \
  "${DOCKER_ROOT}/host/lib" \
  "${DOCKER_ROOT}/host/usr/src" \
  "${DOCKER_ROOT}/host/usr/include" \
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

KERNEL_RELEASE="${PATCHWEAVER_KERNEL_RELEASE:-$(uname -r)}"
PREPARED_SOURCE="/home/patchweaver/kernel-src-prepared/${KERNEL_RELEASE}"
if [[ -d "${PREPARED_SOURCE}" && -f "${PREPARED_SOURCE}/Module.symvers" ]]; then
  "${HOST_PYTHON_BIN}" - "${DOCKER_ROOT}/config/build.yaml" "${PREPARED_SOURCE}" <<'PY'
from pathlib import Path
import sys
import yaml

config_path = Path(sys.argv[1])
prepared_source = sys.argv[2]
payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
payload["prepared_kernel_src_dir"] = prepared_source
priority = list(payload.get("build_source_priority") or [])
if "prepared_kernel_src_dir" not in priority:
    insert_at = priority.index("clean_kernel_src_dir") + 1 if "clean_kernel_src_dir" in priority else 0
    priority.insert(insert_at, "prepared_kernel_src_dir")
payload["build_source_priority"] = priority
extra_args = list(payload.get("kpatch_build_extra_args") or [])
if "--skip-compiler-check" not in extra_args:
    extra_args.append("--skip-compiler-check")
payload["kpatch_build_extra_args"] = extra_args
extra_env = dict(payload.get("kpatch_build_env") or {})
extra_env.setdefault("HOSTLDFLAGS", "-no-pie")
payload["kpatch_build_env"] = extra_env
config_path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
PY
fi

STABLE_SOURCE_GIT_DIR="${PATCHWEAVER_STABLE_SOURCE_GIT_DIR:-${DOCKER_ROOT}/stable/linux}"
if [[ -d "${STABLE_SOURCE_GIT_DIR}/.git" ]]; then
  "${HOST_PYTHON_BIN}" - "${DOCKER_ROOT}/config/build.yaml" "${STABLE_SOURCE_GIT_DIR}" <<'PY'
from pathlib import Path
import sys
import yaml

config_path = Path(sys.argv[1])
stable_source_git_dir = sys.argv[2]
payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
payload["stable_source_git_dir"] = stable_source_git_dir
config_path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
PY
fi

link_path /lib/modules "${DOCKER_ROOT}/host/lib/modules"
link_path /usr/include "${DOCKER_ROOT}/host/usr/include"
link_path /usr/src/kernels "${DOCKER_ROOT}/host/usr/src/kernels"
link_path /usr/lib/debug "${DOCKER_ROOT}/host/usr/lib/debug"
link_path /opt/kernel-src "${DOCKER_ROOT}/host/opt/kernel-src"
link_path /home/patchweaver/kernel-src-prepared "${DOCKER_ROOT}/host/home/patchweaver/kernel-src-prepared"
link_path /usr/bin/kpatch-build "${DOCKER_ROOT}/host/usr/bin/kpatch-build"
link_path /usr/libexec/kpatch "${DOCKER_ROOT}/host/usr/libexec/kpatch"
link_path /usr/share/kpatch "${DOCKER_ROOT}/host/usr/share/kpatch"

printf 'PatchWeaver Docker host root prepared: %s\n' "${DOCKER_ROOT}"
