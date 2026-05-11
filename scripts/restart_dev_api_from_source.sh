#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

API_IMAGE="${PATCHWEAVER_DEV_API_IMAGE:-patchweaver:dev}"
API_CONTAINER="${PATCHWEAVER_DEV_API_CONTAINER:-patchweaver-dev-api}"
API_HOST_PORT="${PATCHWEAVER_DEV_API_HOST_PORT:-18086}"
API_CONTAINER_PORT="${PATCHWEAVER_DEV_API_CONTAINER_PORT:-18084}"
API_PROFILE="${PATCHWEAVER_PROFILE:-full}"
DOCKER_ROOT="${PATCHWEAVER_DOCKER_ROOT:-/usr/local/patchweaver}"
HOST_ROOT="${PATCHWEAVER_HOST_ROOT:-${DOCKER_ROOT}}"
DEV_NETWORK="${PATCHWEAVER_DEV_NETWORK:-patchweaver-dev-net}"

# Dev containers may not have the exact distro compiler used for the target
# kernel. Keep this opt-in to the dev channel and never apply it to test.
KPATCH_EXTRA_ARGS="${PATCHWEAVER_KPATCH_BUILD_EXTRA_ARGS:---skip-compiler-check}"
KPATCH_BUILD_ENV="${PATCHWEAVER_KPATCH_BUILD_ENV:-HOSTLDFLAGS=-no-pie}"

if ! docker image inspect "${API_IMAGE}" >/dev/null 2>&1; then
  echo "missing dev image: ${API_IMAGE}" >&2
  exit 1
fi

docker network inspect "${DEV_NETWORK}" >/dev/null 2>&1 || docker network create "${DEV_NETWORK}" >/dev/null

PATCHWEAVER_DOCKER_ROOT="${DOCKER_ROOT}" bash "${PROJECT_ROOT}/scripts/prepare_docker_host_root.sh"

if docker ps -a --format '{{.Names}}' | grep -Fxq "${API_CONTAINER}"; then
  docker rm -f "${API_CONTAINER}" >/dev/null
fi

tool_mounts=()
if [[ "${PATCHWEAVER_DEV_MOUNT_HOST_BINUTILS:-0}" = "1" ]]; then
  for tool in strings objcopy objdump readelf nm ar strip; do
    if tool_path="$(command -v "${tool}" 2>/dev/null)"; then
      tool_mounts+=(-v "${tool_path}:${tool_path}:ro")
    fi
  done
fi
docker run -d \
  --name "${API_CONTAINER}" \
  --privileged \
  --network "${DEV_NETWORK}" \
  -p "${API_HOST_PORT}:${API_CONTAINER_PORT}" \
  -e "PATCHWEAVER_PROFILE=${API_PROFILE}" \
  -e "PATCHWEAVER_BAILIAN_API_KEY=${PATCHWEAVER_BAILIAN_API_KEY:-}" \
  -e "PATCHWEAVER_HOST_ROOT=${HOST_ROOT}" \
  -e "PATCHWEAVER_API_PORT=${API_CONTAINER_PORT}" \
  -e "PATCHWEAVER_KPATCH_BUILD_EXTRA_ARGS=${KPATCH_EXTRA_ARGS}" \
  -e "PATCHWEAVER_KPATCH_BUILD_ENV=${KPATCH_BUILD_ENV}" \
  -e PYTHONIOENCODING=utf-8 \
  -e PYTHONUTF8=1 \
  -v "${PROJECT_ROOT}/patchweaver:/app/patchweaver" \
  -v "${PROJECT_ROOT}/pyproject.toml:/app/pyproject.toml:ro" \
  -v "${DOCKER_ROOT}/config:/app/config:ro" \
  -v "${DOCKER_ROOT}/data:/app/data" \
  -v "${DOCKER_ROOT}/workspaces:/app/workspaces" \
  -v "${DOCKER_ROOT}/docs/submission:/app/docs/submission" \
  -v "${DOCKER_ROOT}/evaluations:/app/evaluations:ro" \
  -v "${DOCKER_ROOT}/host/lib/modules:/lib/modules:ro" \
  -v "${DOCKER_ROOT}/host/usr/src/kernels:/usr/src/kernels:ro" \
  -v "${DOCKER_ROOT}/host/usr/lib/debug:/usr/lib/debug:ro" \
  -v "${DOCKER_ROOT}/host/opt/kernel-src:/opt/kernel-src:ro" \
  -v "${DOCKER_ROOT}/host/home/patchweaver/kernel-src-prepared:/home/patchweaver/kernel-src-prepared:ro" \
  -v "${DOCKER_ROOT}/host/usr/bin/kpatch-build:/usr/bin/kpatch-build:ro" \
  -v "${DOCKER_ROOT}/host/usr/libexec/kpatch:/usr/libexec/kpatch" \
  -v "${DOCKER_ROOT}/host/usr/share/kpatch:/usr/share/kpatch:ro" \
  "${tool_mounts[@]}" \
  "${API_IMAGE}" \
  python -m patchweaver serve-api --host 0.0.0.0 --port "${API_CONTAINER_PORT}" --foreground

for _ in {1..30}; do
  if curl -fsS "http://127.0.0.1:${API_HOST_PORT}/healthz" >/dev/null; then
    echo "dev API ready at http://127.0.0.1:${API_HOST_PORT}"
    exit 0
  fi
  sleep 2
done

docker logs --tail 100 "${API_CONTAINER}" >&2 || true
echo "dev API did not become healthy on port ${API_HOST_PORT}" >&2
exit 1
