#!/usr/bin/env sh
set -eu

HOST_ROOT="${PATCHWEAVER_DOCKER_ROOT:-${PATCHWEAVER_HOST_ROOT:-/usr/local/patchweaver}}"
NETWORK="${PATCHWEAVER_DOCKER_NETWORK:-patchweaver-net}"
API_IMAGE="${PATCHWEAVER_API_IMAGE:-patchweaver:local}"
WEB_IMAGE="${PATCHWEAVER_WEB_IMAGE:-patchweaver-web:local}"
WEB_PORT="${PATCHWEAVER_WEB_PORT:-18085}"
API_CONTAINER="${PATCHWEAVER_API_CONTAINER:-patchweaver-api}"
WEB_CONTAINER="${PATCHWEAVER_WEB_CONTAINER:-patchweaver-web}"
KERNEL_RELEASE="${PATCHWEAVER_KERNEL_RELEASE:-$(uname -r)}"
KPATCH_EXTRA_ARGS="${PATCHWEAVER_KPATCH_BUILD_EXTRA_ARGS:---skip-compiler-check}"
KPATCH_BUILD_ENV="${PATCHWEAVER_KPATCH_BUILD_ENV:-HOSTLDFLAGS=-no-pie}"

require_path() {
  if [ ! -e "$1" ]; then
    echo "missing required path: $1" >&2
    exit 20
  fi
}

require_path "$HOST_ROOT"
require_path "$HOST_ROOT/host/usr/bin/kpatch-build"
require_path "$HOST_ROOT/host/usr/libexec/kpatch"
require_path "$HOST_ROOT/host/usr/share/kpatch"
require_path "$HOST_ROOT/host/opt/kernel-src"
require_path "$HOST_ROOT/host/usr/src/kernels/$KERNEL_RELEASE"
require_path "$HOST_ROOT/host/usr/lib/debug/lib/modules/$KERNEL_RELEASE/vmlinux"

mkdir -p "$HOST_ROOT/data" "$HOST_ROOT/workspaces" "$HOST_ROOT/data/maintenance"
docker network inspect "$NETWORK" >/dev/null 2>&1 || docker network create "$NETWORK" >/dev/null

docker rm -f "$WEB_CONTAINER" >/dev/null 2>&1 || true
docker rm -f "$API_CONTAINER" >/dev/null 2>&1 || true

docker run -d \
  --name "$API_CONTAINER" \
  --network "$NETWORK" \
  --privileged \
  -e PATCHWEAVER_PROFILE="${PATCHWEAVER_PROFILE:-demo}" \
  -e PATCHWEAVER_HOST_ROOT="$HOST_ROOT" \
  -e PATCHWEAVER_KERNEL_RELEASE="$KERNEL_RELEASE" \
  -e PATCHWEAVER_KPATCH_BUILD_EXTRA_ARGS="$KPATCH_EXTRA_ARGS" \
  -e PATCHWEAVER_KPATCH_BUILD_ENV="$KPATCH_BUILD_ENV" \
  -e PYTHONIOENCODING=utf-8 \
  -e PYTHONUTF8=1 \
  -v "$HOST_ROOT/data:/app/data" \
  -v "$HOST_ROOT/workspaces:/app/workspaces" \
  -v "$HOST_ROOT/docs/submission:/app/docs/submission" \
  -v "$HOST_ROOT/config:/app/config:ro" \
  -v "$HOST_ROOT/evaluations:/app/evaluations:ro" \
  -v "$HOST_ROOT/host/lib/modules:/lib/modules:ro" \
  -v "$HOST_ROOT/host/usr/src/kernels:/usr/src/kernels:ro" \
  -v "$HOST_ROOT/host/usr/lib/debug:/usr/lib/debug:ro" \
  -v "$HOST_ROOT/host/opt/kernel-src:/opt/kernel-src:ro" \
  -v "$HOST_ROOT/host/home/patchweaver/kernel-src-prepared:/home/patchweaver/kernel-src-prepared:ro" \
  -v "$HOST_ROOT/host/usr/bin/kpatch-build:/usr/bin/kpatch-build:ro" \
  -v "$HOST_ROOT/host/usr/libexec/kpatch:/usr/libexec/kpatch" \
  -v "$HOST_ROOT/host/usr/share/kpatch:/usr/share/kpatch:ro" \
  "$API_IMAGE" \
  patchweaver serve-api --host 0.0.0.0 --port 18084 --foreground >/dev/null

for i in $(seq 1 40); do
  if docker run --rm --network "$NETWORK" docker.1ms.run/library/nginx:1.27-alpine wget -qO- "http://$API_CONTAINER:18084/healthz" >/dev/null 2>&1; then
    break
  fi
  if [ "$i" = "40" ]; then
    docker logs --tail 120 "$API_CONTAINER" || true
    exit 21
  fi
  sleep 1
done

docker run -d \
  --name "$WEB_CONTAINER" \
  --network "$NETWORK" \
  -p "$WEB_PORT:18085" \
  "$WEB_IMAGE" >/dev/null

for i in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:$WEB_PORT/console/" >/dev/null; then
    echo "PatchWeaver Web repaired: http://$(hostname -I | awk '{print $1}'):$WEB_PORT/console/"
    exit 0
  fi
  sleep 1
done

docker logs --tail 120 "$WEB_CONTAINER" || true
exit 22
