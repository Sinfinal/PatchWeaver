"""Web 控制台使用的环境诊断服务"""

from __future__ import annotations

import importlib.util
import json
import os
import platform
import re
import stat
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from patchweaver.api.deps import ApiContext
from patchweaver.builder.orchestrator import BuildOrchestrator
from patchweaver.prompting.model_client import ModelClientError, OpenAICompatibleChatClient
from patchweaver.runtime_inspector import collect_machine_profile
from patchweaver.skills.source_policy import resolve_skill_roots
from patchweaver.utils.path_policy import to_project_relative

_SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|password|passwd|credential|secret)\s*[:=]\s*[^ \n\r\t]+"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{8,}"),
]


class DoctorApiService:
    """负责生成并缓存 Web 端使用的诊断结果"""

    def __init__(self, context: ApiContext) -> None:
        """保存 API 共享上下文"""

        self.context = context
        self.cache_path = (context.runtime.data_dir / "traces" / "doctor_latest.json").resolve()

    def get_report(self, *, refresh: bool = False) -> dict[str, Any]:
        """读取最近一次诊断结果，必要时重新生成"""

        if not refresh and self.cache_path.exists():
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
            if self._cached_report_is_current(payload):
                return payload
        payload = self._build_report()
        self.context.doctor_writer.write(payload, self.cache_path)
        return payload

    def _cached_report_is_current(self, payload: dict[str, Any]) -> bool:
        """判断缓存报告是否包含当前 Web 诊断需要的检查项"""

        if getattr(self.context, "models_config", None) is None:
            return True
        checks = payload.get("checks")
        if not isinstance(checks, list):
            return False
        return (
            any(item.get("category") == "model_backend" and item.get("name") == "bailian_chat" for item in checks if isinstance(item, dict))
            and any(item.get("name") == "source_tree_mutability" for item in checks if isinstance(item, dict))
        )

    def repair_environment(self) -> dict[str, Any]:
        """执行 Web 可触发的安全修复，并生成宿主机级修复脚本"""

        started_at = datetime.now(timezone.utc)
        before = self.get_report(refresh=True)
        actions: list[dict[str, Any]] = []

        runtime = self.context.runtime
        directory_targets = [
            ("workspace_root", "工作区目录", runtime.workspace_root),
            ("data_dir", "数据目录", runtime.data_dir),
            ("manifest_dir", "Manifest 目录", runtime.manifest_dir),
            ("doctor_trace_dir", "诊断缓存目录", runtime.data_dir / "traces"),
            ("maintenance_dir", "维护脚本目录", runtime.data_dir / "maintenance"),
            ("workspace_skill_root", "工作区 Skill 目录", self.context.project_root / "workspaces" / "_shared_skills"),
        ]
        for name, label, path in directory_targets:
            actions.append(self._ensure_directory(name=name, label=label, path=path))

        script = self._render_host_repair_script()
        script_path = (runtime.data_dir / "maintenance" / "repair_docker_web_environment.sh").resolve()
        actions.append(self._write_repair_script(path=script_path, content=script))

        host_repair_executed = False
        host_repair_result: dict[str, Any] | None = None
        if os.environ.get("PATCHWEAVER_ENABLE_DOCTOR_HOST_REPAIR") == "1":
            host_repair_result = self._try_run_host_repair_script(script_path)
            host_repair_executed = bool(host_repair_result.get("executed"))
            actions.append(host_repair_result)

        after = self.get_report(refresh=True)
        remaining_errors = [item for item in after["checks"] if item.get("status") == "error"]
        status = "fixed" if not remaining_errors else "requires_host_redeploy"
        if remaining_errors and host_repair_executed:
            status = "partial"

        payload = {
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "summary": {
                "before": before["summary"],
                "after": after["summary"],
                "remaining_error_count": len(remaining_errors),
            },
            "actions": actions,
            "remaining_errors": remaining_errors,
            "script": {
                "path": self._path(script_path),
                "content": script,
                "auto_execute_enabled": os.environ.get("PATCHWEAVER_ENABLE_DOCTOR_HOST_REPAIR") == "1",
                "host_repair_executed": host_repair_executed,
            },
            "report": after,
        }
        result_path = (runtime.data_dir / "maintenance" / "doctor_repair_latest.json").resolve()
        result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return payload

    def _build_report(self) -> dict[str, Any]:
        """整理运行时、依赖和构建环境检查结果"""

        runtime = self.context.runtime
        build_env = BuildOrchestrator(self.context.build_config).probe_environment(workspace_root=runtime.workspace_root.resolve())
        machine_profile = collect_machine_profile(self.context.build_config, build_env=build_env)
        checks: list[dict[str, Any]] = []

        for module_name, label in {
            "fastapi": "FastAPI",
            "uvicorn": "Uvicorn",
            "typer": "Typer",
            "pydantic": "Pydantic",
            "yaml": "PyYAML",
        }.items():
            installed = importlib.util.find_spec(module_name) is not None
            checks.append(self._check("python_module", module_name, f"Python 模块 `{module_name}`", installed, label))

        for filename in [
            "system.yaml",
            "profiles.yaml",
            "build.yaml",
            "verify.yaml",
            "skills.yaml",
            "prompts.yaml",
            "rules.yaml",
            "logging.yaml",
        ]:
            path = runtime.config_dir / filename
            checks.append(self._check("config_file", filename, f"配置文件 `{filename}`", path.exists(), self._path(path)))

        checks.extend(
            [
                self._check("filesystem", "workspace_root", "工作区目录", runtime.workspace_root.exists(), self._path(runtime.workspace_root)),
                self._check("filesystem", "database_path", "SQLite 数据库", runtime.database_path.exists(), self._path(runtime.database_path)),
                self._check("filesystem", "manifest_dir", "Manifest 目录", runtime.manifest_dir.exists(), self._path(runtime.manifest_dir)),
            ]
        )

        for source_layer, root in resolve_skill_roots(self.context.project_root):
            checks.append(
                self._check(
                    "skill_root",
                    source_layer,
                    f"Skill 目录 `{source_layer}`",
                    root.exists(),
                    self._path(root),
                    failed_status="warn",
                )
            )

        for raw_dir in self.context.prompts_config.bootstrap_fragment_dirs:
            bootstrap_dir = (self.context.project_root / raw_dir).resolve()
            checks.append(
                self._check(
                    "prompt_root",
                    raw_dir,
                    f"Bootstrap 目录 `{raw_dir}`",
                    bootstrap_dir.exists(),
                    self._path(bootstrap_dir),
                    failed_status="warn",
                )
            )

        checks.extend(self._build_backend_checks(build_env))
        checks.extend(self._model_backend_checks())
        summary = {
            "total": len(checks),
            "ok": sum(1 for item in checks if item["status"] == "ok"),
            "warn": sum(1 for item in checks if item["status"] == "warn"),
            "error": sum(1 for item in checks if item["status"] == "error"),
        }

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "runtime": {
                "project_root": self._path(runtime.project_root),
                "workspace_root": self._path(runtime.workspace_root),
                "database_path": self._path(runtime.database_path),
                "manifest_dir": self._path(runtime.manifest_dir),
                "default_kernel": runtime.default_kernel,
                "detected_target_kernel": machine_profile.build_target_kernel,
                "detected_target_kernel_source": machine_profile.build_target_kernel_source,
                "machine_kernel": machine_profile.machine_kernel,
                "machine_arch": machine_profile.machine_arch,
                "max_attempts": runtime.max_attempts,
                "python_version": platform.python_version(),
            },
            "machine_profile": machine_profile.model_dump(mode="json"),
            "build_env": build_env,
            "checks": checks,
            "summary": summary,
        }

    def _build_backend_checks(self, build_env: dict[str, Any]) -> list[dict[str, Any]]:
        """把构建环境快照折叠成一组统一检查项"""

        checks = [
            self._check("build_backend", "backend", "构建后端", True, build_env["backend"]),
            self._check(
                "build_backend",
                "builder",
                f"构建命令 `{build_env['builder_cmd']}`",
                bool(build_env.get("builder_ok")),
                build_env.get("builder_path") or "未找到",
                failed_status="error",
            ),
            self._check(
                "build_backend",
                "selected_source_dir",
                "当前运行机源码目录",
                bool(build_env.get("selected_source_ok")),
                self._path_text(build_env.get("selected_source_dir")) or "未找到",
                failed_status="error",
            ),
            self._check(
                "build_backend",
                "config_path",
                "当前运行机内核配置文件",
                bool(build_env.get("config_ok")),
                self._path_text(build_env.get("config_path")) or "未找到",
                failed_status="error",
            ),
            self._check(
                "build_backend",
                "vmlinux_path",
                "当前运行机 vmlinux 文件",
                bool(build_env.get("vmlinux_ok")),
                self._path_text(build_env.get("vmlinux_path")) or "未找到",
                failed_status="error",
            ),
        ]

        mutability = build_env.get("source_mutability") or {}
        writable = build_env.get("writable_build_readiness") or {}

        if mutability.get("baseline_ready") is not None:
            if mutability.get("direct_build_usable"):
                src_status = "ok"
                src_detail = "源码树可直接用于 kpatch-build"
            elif mutability.get("baseline_ready"):
                src_status = "warn"
                src_detail = f"源码树为只读基线，系统将自动创建 attempt 级可写构建树后再构建。{mutability.get('reason') or ''}"
            else:
                src_status = "error"
                src_detail = mutability.get("reason") or "源码基线不完整"
            checks.append({
                "category": "build_backend",
                "name": "source_tree_mutability",
                "label": "源码树构建可用性",
                "ok": src_status == "ok",
                "status": src_status,
                "detail": src_detail,
            })

        if writable.get("ready") is not None:
            checks.append({
                "category": "build_backend",
                "name": "writable_build_readiness",
                "label": "可写构建树就绪",
                "ok": bool(writable.get("ready")),
                "status": "ok" if writable.get("ready") else "error",
                "detail": writable.get("reason") or ("workspace 可创建 attempt 级可写构建树" if writable.get("ready") else "无法创建可写构建树"),
            })

        return checks

    def _model_backend_checks(self) -> list[dict[str, Any]]:
        """检查 Web/Agent 依赖的大模型后端是否可用"""

        models_config = getattr(self.context, "models_config", None)
        if models_config is None:
            return []

        env_var = str(getattr(models_config, "api_key_env", "PATCHWEAVER_BAILIAN_API_KEY"))
        remediation = self._model_backend_remediation(env_var)
        metadata_base = {
            "provider": getattr(models_config, "provider", "unknown"),
            "endpoint_mode": getattr(models_config, "endpoint_mode", "unknown"),
            "base_url": getattr(models_config, "base_url", ""),
            "api_key_env": env_var,
            "input_redacted": True,
            "full_log_sent": False,
        }

        api_key_status = models_config.api_key_status()
        metadata_base["api_key_source"] = api_key_status.get("api_key_source")
        metadata_base["api_key_ready"] = bool(api_key_status.get("api_key_ready"))
        api_key = models_config.resolve_api_key()
        if not api_key:
            return [
                self._check(
                    "model_backend",
                    "bailian_chat",
                    "大模型响应",
                    False,
                    f"未检测到环境变量 {env_var}，模型能力不可用",
                    failed_status="error",
                    remediation=remediation,
                    metadata=metadata_base,
                )
            ]

        if getattr(models_config, "endpoint_mode", None) != "openai_compatible":
            return [
                self._check(
                    "model_backend",
                    "bailian_chat",
                    "大模型响应",
                    False,
                    "当前模型 endpoint_mode 暂不支持 Web 健康探测",
                    failed_status="warn",
                    remediation=remediation,
                    metadata=metadata_base,
                )
            ]

        model_name = (
            getattr(models_config, "development_model", "")
            or getattr(models_config, "default_model", "")
            or getattr(models_config, "delivery_model", "")
        )
        timeout_sec = self._model_probe_timeout_sec()
        metadata = {**metadata_base, "model": model_name, "timeout_sec": timeout_sec}
        try:
            client = OpenAICompatibleChatClient(
                base_url=str(getattr(models_config, "base_url", "")),
                api_key=api_key,
                timeout_sec=timeout_sec,
            )
            result = client.chat_json(
                model=model_name,
                system_prompt="Return one JSON object only. The object must be {\"ok\": true}.",
                user_prompt='{"check":"patchweaver_model_health","expected":"json_ok"}',
                temperature=0.0,
            )
            metadata["response_id"] = result.response_id
            metadata["model_name"] = result.model_name or model_name
            metadata["usage"] = result.usage
            return [
                self._check(
                    "model_backend",
                    "bailian_chat",
                    "大模型响应",
                    True,
                    f"模型响应正常，model={metadata['model_name']}",
                    remediation=remediation,
                    metadata=metadata,
                )
            ]
        except (ModelClientError, OSError, TimeoutError, ValueError, TypeError) as exc:
            safe_detail = self._redact_secret_text(str(exc))[:500]
            metadata["failure_reason"] = safe_detail
            return [
                self._check(
                    "model_backend",
                    "bailian_chat",
                    "大模型响应",
                    False,
                    f"模型接口未响应或返回异常: {safe_detail}",
                    failed_status="error",
                    remediation=remediation,
                    metadata=metadata,
                )
            ]

    def _model_probe_timeout_sec(self) -> int:
        """读取模型健康探测超时时间，避免 doctor 长时间阻塞"""

        raw_value = os.environ.get("PATCHWEAVER_DOCTOR_MODEL_TIMEOUT_SEC", "12").strip()
        try:
            return max(3, min(30, int(raw_value)))
        except ValueError:
            return 12

    def _model_backend_remediation(self, env_var: str) -> dict[str, Any]:
        """返回 Web 弹窗可直接展示的大模型配置修复步骤"""

        return {
            "title": "大模型连接配置",
            "env_var": env_var,
            "steps": [
                f"在启动 PatchWeaver API 的宿主机或容器环境中设置 {env_var}",
                "重启 API 服务或 Docker 容器，让新环境变量进入进程环境",
                "如使用 systemd，请执行 daemon-reload 后 restart 对应服务",
                "回到环境诊断页面，点击重新执行诊断确认模型响应正常",
            ],
            "commands": [
                f"export {env_var}='<your-bailian-api-key>'",
                "docker restart patchweaver-dev-api",
                "docker restart patchweaver-api",
                "systemctl daemon-reload && systemctl restart patchweaver-api",
            ],
            "notes": [
                "不要把 API Key 写入仓库或报告",
                "如果使用 compose 部署，请把环境变量加入 API 服务的 environment 或 env_file",
                "Web 容器只负责展示，关键是重启 API 容器",
            ],
        }

    def _ensure_directory(self, *, name: str, label: str, path: Path) -> dict[str, Any]:
        """确保 Web 进程权限范围内可修复的目录存在"""

        existed = path.exists()
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return {
                "name": name,
                "label": label,
                "status": "failed",
                "detail": f"创建失败: {exc}",
                "path": self._path(path),
            }
        return {
            "name": name,
            "label": label,
            "status": "already_ok" if existed else "fixed",
            "detail": "目录已存在" if existed else "目录已创建",
            "path": self._path(path),
        }

    def _write_repair_script(self, *, path: Path, content: str) -> dict[str, Any]:
        """写入可复制执行的 Docker 环境修复脚本"""

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except OSError as exc:
            return {
                "name": "host_repair_script",
                "label": "宿主机 Docker 修复脚本",
                "status": "failed",
                "detail": f"写入失败: {exc}",
                "path": self._path(path),
            }
        return {
            "name": "host_repair_script",
            "label": "宿主机 Docker 修复脚本",
            "status": "written",
            "detail": "已生成脚本；如果错误仍然来自缺少 kpatch-build、源码、.config 或 vmlinux，需要用该脚本重启 Docker API/Web 容器。",
            "path": self._path(path),
        }

    def _try_run_host_repair_script(self, script_path: Path) -> dict[str, Any]:
        """在明确开启开关时尝试执行宿主机级修复脚本"""

        docker_socket = Path("/var/run/docker.sock")
        if not docker_socket.exists():
            return {
                "name": "host_repair_execute",
                "label": "执行宿主机 Docker 修复",
                "status": "skipped",
                "executed": False,
                "detail": "未挂载 /var/run/docker.sock，Web 进程不能直接重启宿主机 Docker 容器。",
            }
        command = ["/bin/sh", str(script_path)]
        try:
            result = subprocess.run(
                command,
                cwd=self.context.project_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {
                "name": "host_repair_execute",
                "label": "执行宿主机 Docker 修复",
                "status": "failed",
                "executed": False,
                "detail": str(exc),
            }
        return {
            "name": "host_repair_execute",
            "label": "执行宿主机 Docker 修复",
            "status": "ok" if result.returncode == 0 else "failed",
            "executed": True,
            "detail": f"退出码 {result.returncode}",
            "stdout_excerpt": result.stdout[-4000:],
            "stderr_excerpt": result.stderr[-4000:],
        }

    def _render_host_repair_script(self) -> str:
        """生成带宿主机构建材料挂载的 Docker Web/API 修复脚本"""

        return """#!/usr/bin/env sh
set -eu

HOST_ROOT="${PATCHWEAVER_HOST_ROOT:-/home/patchweaver/current}"
NETWORK="${PATCHWEAVER_DOCKER_NETWORK:-patchweaver-net}"
API_IMAGE="${PATCHWEAVER_API_IMAGE:-patchweaver:local}"
WEB_IMAGE="${PATCHWEAVER_WEB_IMAGE:-patchweaver-web:local}"
WEB_PORT="${PATCHWEAVER_WEB_PORT:-18085}"
API_CONTAINER="${PATCHWEAVER_API_CONTAINER:-patchweaver-api}"
WEB_CONTAINER="${PATCHWEAVER_WEB_CONTAINER:-patchweaver-web}"
KERNEL_RELEASE="${PATCHWEAVER_KERNEL_RELEASE:-$(uname -r)}"

require_path() {
  if [ ! -e "$1" ]; then
    echo "missing required path: $1" >&2
    exit 20
  fi
}

require_path "$HOST_ROOT"
require_path /usr/bin/kpatch-build
require_path /usr/libexec/kpatch
require_path /usr/share/kpatch
require_path /opt/kernel-src
require_path "/usr/src/kernels/$KERNEL_RELEASE"
require_path "/usr/lib/debug/lib/modules/$KERNEL_RELEASE/vmlinux"

mkdir -p "$HOST_ROOT/data" "$HOST_ROOT/workspaces" "$HOST_ROOT/data/maintenance"
docker network inspect "$NETWORK" >/dev/null 2>&1 || docker network create "$NETWORK" >/dev/null

docker rm -f "$WEB_CONTAINER" >/dev/null 2>&1 || true
docker rm -f "$API_CONTAINER" >/dev/null 2>&1 || true

docker run -d \
  --name "$API_CONTAINER" \
  --network "$NETWORK" \
  --privileged \
  -e PATCHWEAVER_PROFILE="${PATCHWEAVER_PROFILE:-demo}" \
  -e PYTHONIOENCODING=utf-8 \
  -e PYTHONUTF8=1 \
  -v "$HOST_ROOT/data:/app/data" \
  -v "$HOST_ROOT/workspaces:/app/workspaces" \
  -v "$HOST_ROOT/config:/app/config:ro" \
  -v "$HOST_ROOT/evaluations:/app/evaluations:ro" \
  -v /lib/modules:/lib/modules:ro \
  -v /usr/src/kernels:/usr/src/kernels:ro \
  -v /usr/lib/debug:/usr/lib/debug:ro \
  -v /opt/kernel-src:/opt/kernel-src:ro \
  -v /home/patchweaver/kernel-src-prepared:/home/patchweaver/kernel-src-prepared:ro \
  -v /usr/bin/kpatch-build:/usr/bin/kpatch-build:ro \
  -v /usr/libexec/kpatch:/usr/libexec/kpatch \
  -v /usr/share/kpatch:/usr/share/kpatch:ro \
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
"""

    def _check(
        self,
        category: str,
        name: str,
        label: str,
        ok: bool,
        detail: str,
        *,
        failed_status: str = "warn",
        remediation: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """构造单条诊断项"""

        payload = {
            "category": category,
            "name": name,
            "label": label,
            "ok": ok,
            "status": "ok" if ok else failed_status,
            "detail": detail,
        }
        if remediation is not None:
            payload["remediation"] = remediation
        if metadata is not None:
            payload["metadata"] = metadata
        return payload

    def _redact_secret_text(self, text: str) -> str:
        """清理可能来自异常文本的密钥片段"""

        redacted = text
        for pattern in _SECRET_PATTERNS:
            redacted = pattern.sub(lambda match: f"{match.group(1) if match.groups() else 'secret'}[REDACTED]", redacted)
        return redacted.replace("。", "")

    def _path(self, value) -> str | None:
        """把项目内路径转换成相对源码根目录表达"""

        return to_project_relative(self.context.project_root, value)

    def _path_text(self, value: str | None) -> str | None:
        """兼容字符串形式的路径字段"""

        return to_project_relative(self.context.project_root, value)
