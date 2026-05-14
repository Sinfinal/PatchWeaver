#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

API_IMAGE="${PATCHWEAVER_DEV_API_IMAGE:-patchweaver:dev}"
API_CONTAINER="${PATCHWEAVER_DEV_API_CONTAINER:-patchweaver-dev-api}"
API_PORT="${PATCHWEAVER_DEV_API_PORT:-18086}"
API_PROFILE="${PATCHWEAVER_PROFILE:-full}"
DOCKER_ROOT="${PATCHWEAVER_DOCKER_ROOT:-/usr/local/patchweaver}"
HOST_ROOT="${PATCHWEAVER_HOST_ROOT:-${DOCKER_ROOT}}"
PYTHON_BASE_IMAGE="${PATCHWEAVER_PYTHON_BASE_IMAGE:-python:3.11-slim}"
BUILD_RETRIES="${PATCHWEAVER_DOCKER_BUILD_RETRIES:-3}"
BUILD_NETWORK="${PATCHWEAVER_DOCKER_BUILD_NETWORK:-host}"

if ! docker buildx version >/dev/null 2>&1; then
  export DOCKER_BUILDKIT=0
fi

PATCHWEAVER_DOCKER_ROOT="${DOCKER_ROOT}" bash "${PROJECT_ROOT}/scripts/prepare_docker_host_root.sh"

build_args=(
  --file "${PROJECT_ROOT}/build/patchweaver/Dockerfile"
  --tag "${API_IMAGE}"
  --build-arg "PYTHON_BASE_IMAGE=${PYTHON_BASE_IMAGE}"
)
if [[ -n "${BUILD_NETWORK}" ]]; then
  build_args+=(--network "${BUILD_NETWORK}")
fi

attempt=1
until docker build "${build_args[@]}" "${PROJECT_ROOT}"; do
  if (( attempt >= BUILD_RETRIES )); then
    echo "dev API image build failed after ${attempt} attempt(s)" >&2
    exit 1
  fi
  echo "dev API image build failed, retrying $((attempt + 1))/${BUILD_RETRIES}" >&2
  attempt=$((attempt + 1))
  sleep 5
done

if docker ps -a --format '{{.Names}}' | grep -Fxq "${API_CONTAINER}"; then
  docker rm -f "${API_CONTAINER}" >/dev/null
fi

docker run -d \
  --name "${API_CONTAINER}" \
  --privileged \
  -p "${API_PORT}:${API_PORT}" \
  -e "PATCHWEAVER_PROFILE=${API_PROFILE}" \
  -e "PATCHWEAVER_BAILIAN_API_KEY=${PATCHWEAVER_BAILIAN_API_KEY:-}" \
  -e "PATCHWEAVER_HOST_ROOT=${HOST_ROOT}" \
  -e "PATCHWEAVER_API_PORT=${API_PORT}" \
  -e PYTHONIOENCODING=utf-8 \
  -e PYTHONUTF8=1 \
  -v "${DOCKER_ROOT}/data:/app/data" \
  -v "${DOCKER_ROOT}/workspaces:/app/workspaces" \
  -v "${DOCKER_ROOT}/docs/submission:/app/docs/submission" \
  -v "${DOCKER_ROOT}/config:/app/config:ro" \
  -v "${DOCKER_ROOT}/evaluations:/app/evaluations:ro" \
  -v "${DOCKER_ROOT}/host/lib/modules:/lib/modules:ro" \
  -v "${DOCKER_ROOT}/host/usr/include:/usr/include:ro" \
  -v "${DOCKER_ROOT}/host/usr/src/kernels:/usr/src/kernels:ro" \
  -v "${DOCKER_ROOT}/host/usr/lib/debug:/usr/lib/debug:ro" \
  -v "${DOCKER_ROOT}/host/opt/kernel-src:/opt/kernel-src:ro" \
  -v "${DOCKER_ROOT}/host/home/patchweaver/kernel-src-prepared:/home/patchweaver/kernel-src-prepared:ro" \
  -v "${DOCKER_ROOT}/host/usr/bin/kpatch-build:/usr/bin/kpatch-build:ro" \
  -v "${DOCKER_ROOT}/host/usr/libexec/kpatch:/usr/libexec/kpatch" \
  -v "${DOCKER_ROOT}/host/usr/share/kpatch:/usr/share/kpatch:ro" \
  "${API_IMAGE}" \
  python -m patchweaver serve-api --host 0.0.0.0 --port "${API_PORT}" --foreground

for _ in {1..30}; do
  if curl -fsS "http://127.0.0.1:${API_PORT}/healthz" >/dev/null; then
    echo "dev API ready at http://127.0.0.1:${API_PORT}"
    exit 0
  fi
  sleep 2
done

docker logs --tail 100 "${API_CONTAINER}" >&2 || true
echo "dev API did not become healthy on port ${API_PORT}" >&2
exit 1
