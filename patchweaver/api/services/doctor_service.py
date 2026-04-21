"""Web 控制台使用的环境诊断服务"""

from __future__ import annotations

import importlib.util
import json
import platform
from datetime import datetime, timezone
from typing import Any

from patchweaver.api.deps import ApiContext
from patchweaver.builder.orchestrator import BuildOrchestrator
from patchweaver.runtime_inspector import collect_machine_profile
from patchweaver.skills.source_policy import resolve_skill_roots
from patchweaver.utils.path_policy import to_project_relative


class DoctorApiService:
    """负责生成并缓存 Web 端使用的诊断结果"""

    def __init__(self, context: ApiContext) -> None:
        """保存 API 共享上下文"""

        self.context = context
        self.cache_path = (context.runtime.data_dir / "traces" / "doctor_latest.json").resolve()

    def get_report(self, *, refresh: bool = False) -> dict[str, Any]:
        """读取最近一次诊断结果，必要时重新生成"""

        if not refresh and self.cache_path.exists():
            return json.loads(self.cache_path.read_text(encoding="utf-8"))
        payload = self._build_report()
        self.context.doctor_writer.write(payload, self.cache_path)
        return payload

    def _build_report(self) -> dict[str, Any]:
        """整理运行时、依赖和构建环境检查结果"""

        runtime = self.context.runtime
        build_env = BuildOrchestrator(self.context.build_config).probe_environment()
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
        return checks

    def _check(
        self,
        category: str,
        name: str,
        label: str,
        ok: bool,
        detail: str,
        *,
        failed_status: str = "warn",
    ) -> dict[str, Any]:
        """构造单条诊断项"""

        return {
            "category": category,
            "name": name,
            "label": label,
            "ok": ok,
            "status": "ok" if ok else failed_status,
            "detail": detail,
        }

    def _path(self, value) -> str | None:
        """把项目内路径转换成相对源码根目录表达"""

        return to_project_relative(self.context.project_root, value)

    def _path_text(self, value: str | None) -> str | None:
        """兼容字符串形式的路径字段"""

        return to_project_relative(self.context.project_root, value)
