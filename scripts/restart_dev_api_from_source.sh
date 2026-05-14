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
AGENT_RUNTIME="${PATCHWEAVER_AGENT_RUNTIME:-langgraph}"
FAILURE_CLASSIFIER="${PATCHWEAVER_FAILURE_CLASSIFIER:-llm}"
USE_HOST_TOOLCHAIN="${PATCHWEAVER_DEV_USE_HOST_TOOLCHAIN:-1}"
STABLE_SOURCE_GIT_DIR="${PATCHWEAVER_STABLE_SOURCE_GIT_DIR:-${DOCKER_ROOT}/stable/linux}"

# Dev containers may not have the exact distro compiler used for the target
# kernel. Keep this opt-in to the dev channel and never apply it to test.
KPATCH_EXTRA_ARGS="${PATCHWEAVER_KPATCH_BUILD_EXTRA_ARGS:---skip-compiler-check}"
KPATCH_BUILD_ENV_DEFAULT="HOSTLDFLAGS=-no-pie HOSTCC=/usr/bin/gcc HOSTCXX=/usr/bin/g++ LD_LIBRARY_PATH=/opt/patchweaver-host-toolchain/lib"
if [[ "${USE_HOST_TOOLCHAIN}" = "1" ]]; then
  KPATCH_BUILD_ENV_DEFAULT="${KPATCH_BUILD_ENV_DEFAULT} CROSS_COMPILE=patchweaver-target-"
fi
KPATCH_BUILD_ENV="${PATCHWEAVER_KPATCH_BUILD_ENV:-${KPATCH_BUILD_ENV_DEFAULT}}"

if ! docker image inspect "${API_IMAGE}" >/dev/null 2>&1; then
  echo "missing dev image: ${API_IMAGE}" >&2
  exit 1
fi

load_bailian_key_from_env_files() {
  if [[ -n "${PATCHWEAVER_BAILIAN_API_KEY:-}" ]]; then
    return
  fi

  local env_file
  local line
  local value
  for env_file in \
    "${PROJECT_ROOT}/.env" \
    "${DOCKER_ROOT}/.env" \
    /etc/patchweaver/patchweaver.env \
    "${HOME:-/root}/.bashrc"; do
    if [[ ! -f "${env_file}" ]] || ! grep -q 'PATCHWEAVER_BAILIAN_API_KEY' "${env_file}"; then
      continue
    fi
    line="$(grep -E '^[[:space:]]*(export[[:space:]]+)?PATCHWEAVER_BAILIAN_API_KEY=' "${env_file}" | tail -n 1 || true)"
    if [[ -z "${line}" ]]; then
      continue
    fi
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line#export }"
    value="${line#PATCHWEAVER_BAILIAN_API_KEY=}"
    value="${value%%#*}"
    value="${value%"${value##*[![:space:]]}"}"
    value="${value%\"}"
    value="${value#\"}"
    value="${value%\'}"
    value="${value#\'}"
    if [[ -n "${value}" ]]; then
      export PATCHWEAVER_BAILIAN_API_KEY="${value}"
      return
    fi
  done
}

load_bailian_key_from_env_files

docker network inspect "${DEV_NETWORK}" >/dev/null 2>&1 || docker network create "${DEV_NETWORK}" >/dev/null

PATCHWEAVER_DOCKER_ROOT="${DOCKER_ROOT}" bash "${PROJECT_ROOT}/scripts/prepare_docker_host_root.sh"

if docker ps -a --format '{{.Names}}' | grep -Fxq "${API_CONTAINER}"; then
  docker rm -f "${API_CONTAINER}" >/dev/null
fi

host_toolchain_mounts=()
host_toolchain_env=()
dev_tool_mounts=()
dev_tool_env=()
KPATCH_BUILD_MOUNT_SOURCE="${DOCKER_ROOT}/host/usr/bin/kpatch-build"
prepare_host_toolchain() {
  local root="${DOCKER_ROOT}/host-toolchain"
  local wrapper_dir="${root}/bin"
  local real_bin_dir="${root}/real-bin"
  local lib_dir="${root}/lib"
  local lib64_dir="${root}/lib64"

  copy_binary_libs() {
    local binary_path="$1"
    local ldd_output
    ldd_output="$(ldd "${binary_path}" 2>/dev/null || true)"
    printf '%s\n' "${ldd_output}" | awk '{ for (i = 1; i <= NF; i++) if ($i ~ /^\//) print $i }' | while read -r lib_path; do
      if [[ -e "${lib_path}" ]]; then
        case "$(basename "${lib_path}")" in
          libc.so.*|ld-linux*.so.*|libpthread.so.*|libdl.so.*|librt.so.*|libm.so.*)
            continue
            ;;
        esac
        cp -L "${lib_path}" "${lib_dir}/$(basename "${lib_path}")" || true
      fi
    done
  }

  copy_kpatch_tool_libs() {
    if [[ ! -d /usr/libexec/kpatch ]]; then
      return
    fi
    local tool_path
    while IFS= read -r tool_path; do
      if [[ -f "${tool_path}" ]]; then
        copy_binary_libs "${tool_path}"
      fi
    done < <(find /usr/libexec/kpatch -type f -perm /111 2>/dev/null || true)
  }

  copy_linker_start_files() {
    local candidate
    local resolved
    local start_file

    for start_file in crt1.o crti.o crtn.o; do
      for candidate in \
        "/usr/lib64/${start_file}" \
        "/lib64/${start_file}" \
        "/usr/lib/x86_64-linux-gnu/${start_file}" \
        "$(gcc -print-file-name="${start_file}" 2>/dev/null || true)"; do
        if [[ -n "${candidate}" && -f "${candidate}" ]]; then
          resolved="$(readlink -f "${candidate}")"
          cp -L "${resolved}" "${lib64_dir}/${start_file}"
          break
        fi
      done
    done

    for candidate in \
      /lib64/libgcc_s.so.1 \
      /usr/lib64/libgcc_s.so.1 \
      /lib/x86_64-linux-gnu/libgcc_s.so.1 \
      /usr/lib/x86_64-linux-gnu/libgcc_s.so.1 \
      "$(gcc -print-file-name=libgcc_s.so.1 2>/dev/null || true)"; do
      if [[ -n "${candidate}" && -f "${candidate}" ]]; then
        resolved="$(readlink -f "${candidate}")"
        cp -L "${resolved}" "${lib64_dir}/libgcc_s.so.1"
        break
      fi
    done

    for runtime_file in libc.so libc.so.6 libc_nonshared.a ld-linux-x86-64.so.2; do
      for candidate in \
        "/usr/lib64/${runtime_file}" \
        "/lib64/${runtime_file}" \
        "/usr/lib/x86_64-linux-gnu/${runtime_file}" \
        "/lib/x86_64-linux-gnu/${runtime_file}"; do
        if [[ -n "${candidate}" && -e "${candidate}" ]]; then
          resolved="$(readlink -f "${candidate}")"
          cp -L "${resolved}" "${lib64_dir}/${runtime_file}"
          break
        fi
      done
    done

    for linker_lib in libcrypto.so libelf.so libz.so libpthread.so libpthread.a libpthread.so.0 libpthread_nonshared.a; do
      for candidate in \
        "/usr/lib64/${linker_lib}" \
        "/lib64/${linker_lib}" \
        "/usr/lib/x86_64-linux-gnu/${linker_lib}" \
        "/lib/x86_64-linux-gnu/${linker_lib}" \
        "$(gcc -print-file-name="${linker_lib}" 2>/dev/null || true)"; do
        if [[ -n "${candidate}" && -e "${candidate}" ]]; then
          resolved="$(readlink -f "${candidate}")"
          cp -L "${resolved}" "${lib64_dir}/${linker_lib}"
          break
        fi
      done
    done
  }

  rm -rf "${root}"
  mkdir -p "${wrapper_dir}" "${real_bin_dir}" "${lib_dir}" "${lib64_dir}" "${root}/usr/lib" "${root}/usr/libexec" "${root}/lib" "${root}/libexec"

  for tool in gcc cc cpp make ld as strings objcopy objdump readelf nm ar strip pahole bc modinfo gawk awk modprobe insmod rmmod lsmod depmod kmod; do
    local tool_path
    tool_path="$(command -v "${tool}" 2>/dev/null || true)"
    if [[ -z "${tool_path}" ]]; then
      printf 'warning: host tool not found, skipped: %s\n' "${tool}" >&2
      continue
    fi
    local resolved_tool
    resolved_tool="$(readlink -f "${tool_path}")"
    cp -L "${resolved_tool}" "${real_bin_dir}/${tool}"
    copy_binary_libs "${resolved_tool}"
  done

  if [[ -d /usr/lib/gcc ]]; then
    cp -a /usr/lib/gcc "${root}/usr/lib/gcc"
  fi
  if [[ -d /usr/libexec/gcc ]]; then
    cp -a /usr/libexec/gcc "${root}/usr/libexec/gcc"
  fi
  if [[ -d "${root}/usr/lib/gcc" ]]; then
    ln -sfn ../usr/lib/gcc "${root}/lib/gcc"
  fi
  if [[ -d "${root}/usr/libexec/gcc" ]]; then
    ln -sfn ../usr/libexec/gcc "${root}/libexec/gcc"
  fi
  ln -sfn /usr/include "${root}/usr/include"
  ln -sfn ../lib64 "${root}/usr/lib64"

  for internal_binary in \
    $(find "${root}/usr/lib/gcc" "${root}/usr/libexec/gcc" -type f -perm /111 2>/dev/null || true); do
    copy_binary_libs "${internal_binary}"
  done
  copy_kpatch_tool_libs

  copy_linker_start_files

  for lib in \
    /lib64/libbfd-*.so \
    /lib64/libctf.so.* \
    /lib64/libctf-nobfd.so.* \
    /lib64/libsframe.so.* \
    /lib64/libopcodes-*.so \
    /lib64/libdebuginfod.so.*; do
    if [[ -e "${lib}" ]]; then
      cp -L "${lib}" "${lib_dir}/$(basename "${lib}")"
    fi
  done

  for tool in gcc cc cpp; do
    if [[ -x "${real_bin_dir}/${tool}" ]]; then
      cat > "${wrapper_dir}/${tool}" <<SH
#!/usr/bin/env sh
export LD_LIBRARY_PATH=/opt/patchweaver-host-toolchain/lib:\${LD_LIBRARY_PATH:-}
export LIBRARY_PATH=/opt/patchweaver-host-toolchain/lib64:/opt/patchweaver-host-toolchain/lib:\${LIBRARY_PATH:-}
exec /opt/patchweaver-host-toolchain/real-bin/${tool} --sysroot=/opt/patchweaver-host-toolchain "\$@"
SH
      chmod +x "${wrapper_dir}/${tool}"
      ln -sfn "${tool}" "${wrapper_dir}/patchweaver-target-${tool}"
    fi
  done

  for tool in make ld as strings objcopy objdump readelf nm ar strip pahole bc modinfo gawk awk modprobe insmod rmmod lsmod depmod kmod; do
    if [[ -x "${real_bin_dir}/${tool}" ]]; then
      cat > "${wrapper_dir}/${tool}" <<SH
#!/usr/bin/env sh
export LD_LIBRARY_PATH=/opt/patchweaver-host-toolchain/lib:\${LD_LIBRARY_PATH:-}
exec /opt/patchweaver-host-toolchain/real-bin/${tool} "\$@"
SH
      chmod +x "${wrapper_dir}/${tool}"
      ln -sfn "${tool}" "${wrapper_dir}/patchweaver-target-${tool}"
    fi
  done
}

prepare_dev_kpatch_wrapper() {
  local root="${DOCKER_ROOT}/dev-bin"
  local source="/usr/bin/kpatch-build"
  local target="${root}/kpatch-build"
  mkdir -p "${root}"
  if [[ ! -x "${source}" ]]; then
    printf 'warning: host kpatch-build not found, wrapper skipped: %s\n' "${source}" >&2
    return
  fi
  cp -L "${source}" "${target}"
  python3 - "${target}" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
old = "sed -i 's/CONFIG_DEBUG_INFO_BTF_MODULES/DISABLED_FOR_KPATCH_BUILD/g' \"$KERNEL_SRCDIR\"/scripts/Makefile.modfinal || die"
new = ": # PatchWeaver dev keeps CONFIG_DEBUG_INFO_BTF_MODULES so struct module layout matches the running kernel"
if old in text:
    text = text.replace(old, new)
path.write_text(text, encoding="utf-8")
PY
  chmod +x "${target}"
  KPATCH_BUILD_MOUNT_SOURCE="${target}"
}

if [[ "${USE_HOST_TOOLCHAIN}" = "1" ]]; then
  prepare_host_toolchain
  prepare_dev_kpatch_wrapper
  host_toolchain_mounts+=(
    -v "${DOCKER_ROOT}/host-toolchain:/opt/patchweaver-host-toolchain:ro"
  )
  dev_tool_mounts+=(
    -v "${DOCKER_ROOT}/dev-bin:/opt/patchweaver-dev-bin:ro"
  )
  host_toolchain_env+=(
    -e "PATH=/usr/local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/opt/patchweaver-host-toolchain/bin"
  )
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
  -e "PATCHWEAVER_AGENT_RUNTIME=${AGENT_RUNTIME}" \
  -e "PATCHWEAVER_FAILURE_CLASSIFIER=${FAILURE_CLASSIFIER}" \
  -e "PATCHWEAVER_STABLE_SOURCE_GIT_DIR=${STABLE_SOURCE_GIT_DIR}" \
  -e "PATCHWEAVER_KPATCH_BUILD_EXTRA_ARGS=${KPATCH_EXTRA_ARGS}" \
  -e "PATCHWEAVER_KPATCH_BUILD_ENV=${KPATCH_BUILD_ENV}" \
  "${host_toolchain_env[@]}" \
  -e PYTHONIOENCODING=utf-8 \
  -e PYTHONUTF8=1 \
  -v "${PROJECT_ROOT}/patchweaver:/app/patchweaver" \
  -v "${PROJECT_ROOT}/pyproject.toml:/app/pyproject.toml:ro" \
  -v "${DOCKER_ROOT}/config:/app/config:ro" \
  -v "${DOCKER_ROOT}/data:/app/data" \
  -v "${DOCKER_ROOT}/workspaces:/app/workspaces" \
  -v "${DOCKER_ROOT}/stable:/usr/local/patchweaver/stable:ro" \
  -v "${DOCKER_ROOT}/docs/submission:/app/docs/submission" \
  -v "${DOCKER_ROOT}/evaluations:/app/evaluations:ro" \
  -v "${DOCKER_ROOT}/host/lib/modules:/lib/modules:ro" \
  -v "${DOCKER_ROOT}/host/usr/include:/usr/include:ro" \
  -v "${DOCKER_ROOT}/host/usr/src/kernels:/usr/src/kernels:ro" \
  -v "${DOCKER_ROOT}/host/usr/lib/debug:/usr/lib/debug:ro" \
  -v "${DOCKER_ROOT}/host/opt/kernel-src:/opt/kernel-src:ro" \
  -v "${DOCKER_ROOT}/host/home/patchweaver/kernel-src-prepared:/home/patchweaver/kernel-src-prepared:ro" \
  -v "${KPATCH_BUILD_MOUNT_SOURCE}:/usr/bin/kpatch-build:ro" \
  -v "${DOCKER_ROOT}/host/usr/libexec/kpatch:/usr/libexec/kpatch" \
  -v "${DOCKER_ROOT}/host/usr/share/kpatch:/usr/share/kpatch:ro" \
  "${host_toolchain_mounts[@]}" \
  "${dev_tool_mounts[@]}" \
  "${tool_mounts[@]}" \
  --entrypoint python \
  "${API_IMAGE}" \
  -m patchweaver serve-api --host 0.0.0.0 --port "${API_CONTAINER_PORT}" --foreground

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
