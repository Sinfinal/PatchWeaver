#!/usr/bin/env bash
set -euo pipefail

echo "PatchWeaver validation smoke"
echo "kernel=$(uname -r)"

if [[ ! -d /sys/kernel/livepatch ]]; then
  echo "missing /sys/kernel/livepatch"
  exit 1
fi

if lsmod | awk '{print $1}' | grep -E '^patchweaver_' >/dev/null; then
  echo "patchweaver livepatch module still loaded after unload"
  lsmod | grep -E '^patchweaver_' || true
  exit 1
fi

if find /sys/kernel/livepatch -mindepth 1 -maxdepth 1 -type d -name 'patchweaver_*' | grep -q .; then
  echo "patchweaver livepatch sysfs entry still present after unload"
  find /sys/kernel/livepatch -mindepth 1 -maxdepth 1 -type d -name 'patchweaver_*' -print
  exit 1
fi

echo "smoke passed"
