#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

WEB_IMAGE="${PATCHWEAVER_DEV_WEB_IMAGE:-patchweaver-web:dev}"
WEB_CONTAINER="${PATCHWEAVER_DEV_WEB_CONTAINER:-patchweaver-dev-web}"
WEB_HOST_PORT="${PATCHWEAVER_DEV_WEB_HOST_PORT:-18087}"
WEB_CONTAINER_PORT="${PATCHWEAVER_DEV_WEB_CONTAINER_PORT:-18085}"
API_CONTAINER="${PATCHWEAVER_DEV_API_CONTAINER:-patchweaver-dev-api}"
API_CONTAINER_PORT="${PATCHWEAVER_DEV_API_CONTAINER_PORT:-18084}"
DEV_NETWORK="${PATCHWEAVER_DEV_NETWORK:-patchweaver-dev-net}"

if ! docker image inspect "${WEB_IMAGE}" >/dev/null 2>&1; then
  echo "missing dev web image: ${WEB_IMAGE}" >&2
  exit 1
fi

if [[ ! -f "${PROJECT_ROOT}/web/dist/index.html" ]]; then
  echo "missing web/dist/index.html, run npm build first" >&2
  exit 1
fi

docker network inspect "${DEV_NETWORK}" >/dev/null 2>&1 || docker network create "${DEV_NETWORK}" >/dev/null

if docker ps -a --format '{{.Names}}' | grep -Fxq "${WEB_CONTAINER}"; then
  docker rm -f "${WEB_CONTAINER}" >/dev/null
fi

docker run -d \
  --name "${WEB_CONTAINER}" \
  --network "${DEV_NETWORK}" \
  -p "${WEB_HOST_PORT}:${WEB_CONTAINER_PORT}" \
  -v "${PROJECT_ROOT}/web/dist:/usr/share/nginx/html/console:ro" \
  "${WEB_IMAGE}" \
  sh -c "cat > /etc/nginx/conf.d/default.conf <<'NGINX'
server {
  listen ${WEB_CONTAINER_PORT};
  server_name _;
  resolver 127.0.0.11 valid=30s ipv6=off;

  root /usr/share/nginx/html;

  location = / {
    return 302 /console/;
  }

  location /console/ {
    try_files \$uri \$uri/ /console/index.html;
  }

  location /api/ {
    set \$patchweaver_api http://${API_CONTAINER}:${API_CONTAINER_PORT};
    proxy_http_version 1.1;
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto \$scheme;
    proxy_pass \$patchweaver_api\$request_uri;
  }

  location = /healthz {
    set \$patchweaver_api http://${API_CONTAINER}:${API_CONTAINER_PORT};
    proxy_http_version 1.1;
    proxy_set_header Host \$host;
    proxy_pass \$patchweaver_api/healthz;
  }
}
NGINX
nginx -g 'daemon off;'"

for _ in {1..30}; do
  if curl -fsS "http://127.0.0.1:${WEB_HOST_PORT}/console/" >/dev/null; then
    curl -fsS "http://127.0.0.1:${WEB_HOST_PORT}/healthz" >/dev/null
    echo "dev Web ready at http://127.0.0.1:${WEB_HOST_PORT}/console/"
    exit 0
  fi
  sleep 2
done

docker logs --tail 100 "${WEB_CONTAINER}" >&2 || true
echo "dev Web did not become healthy on port ${WEB_HOST_PORT}" >&2
exit 1
