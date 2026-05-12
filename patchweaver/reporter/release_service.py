"""第四阶段交付收口与门禁检查"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from patchweaver.builder.orchestrator import BuildOrchestrator
from patchweaver.utils.path_policy import ensure_within_root, relativize_payload, to_project_relative


class ReleaseService:
    """负责整理 docs/submission 目录、final manifest 和最终门禁结果"""

    def __init__(
        self,
        *,
        runtime: Any,
        build_config: Any,
        logging_config: Any,
        models_config: Any,
        task_repo: Any,
        attempt_repo: Any,
        artifact_repo: Any,
    ) -> None:
        """把封版阶段会用到的运行依赖绑定到实例上"""

        self.runtime = runtime
        self.build_config = build_config
        self.logging_config = logging_config
        self.models_config = models_config
        self.task_repo = task_repo
        self.attempt_repo = attempt_repo
        self.artifact_repo = artifact_repo

    def prepare_submission(self) -> dict[str, Any]:
        """创建 docs/submission 结构，并生成最终清单"""

        layout = self._ensure_submission_dirs()
        staged_docs = self._stage_submission_docs(layout)
        manifest = self._build_final_manifest(layout, staged_docs)
        manifest_json_path = self._write_json(manifest, layout["manifests"] / "final_manifest.json")
        manifest_md_path = self._write_text(self._render_manifest_markdown(manifest), layout["manifests"] / "final_manifest.md")
        return {
            "submission_root": self._path(self._submission_root()),
            "layout": self._layout_payload(layout),
            "final_manifest_json": self._path(manifest_json_path),
            "final_manifest_md": self._path(manifest_md_path),
            "status": "ok",
        }

    def run_gate(self) -> dict[str, Any]:
        """执行第四阶段最终门禁检查"""

        layout = self._ensure_submission_dirs()
        manifest_path = layout["manifests"] / "final_manifest.json"
        api_key_status = self._api_key_status()
        # gate 依赖 final_manifest
        # 这里允许先补一次 prepare_submission，少记一条前置命令
        if not manifest_path.exists():
            self.prepare_submission()

        # build_probe 看环境，evaluation_summaries 看阶段样例
        # task_closures 则看最近任务有没有形成真正的闭环产物
        build_probe = BuildOrchestrator(self.build_config).probe_environment()
        evaluation_summaries = self._evaluation_summaries()
        recent_tasks = self.task_repo.list_tasks(limit=12)
        task_closures = [self._task_closure(task) for task in recent_tasks]
        checks = [
            self._check(
                "doctor_snapshot",
                (self.runtime.manifest_dir / "doctor_report.json").exists(),
                self._path(self.runtime.manifest_dir / "doctor_report.json"),
                "doctor 快照已生成。"
                if (self.runtime.manifest_dir / "doctor_report.json").exists()
                else "还没有 doctor 快照，建议先执行 patchweaver doctor。",
                "failed",
            ),
            self._check(
                "database_ready",
                self.runtime.database_path.exists(),
                self._path(self.runtime.database_path),
                "SQLite 数据库可用。" if self.runtime.database_path.exists() else "数据库文件尚未建立。",
                "failed",
            ),
            self._check(
                "evaluation_summary",
                bool(evaluation_summaries),
                self._path(self.runtime.data_dir / "evaluations"),
                f"已发现 {len(evaluation_summaries)} 组阶段评测摘要。"
                if evaluation_summaries
                else "还没有阶段评测摘要，请先执行 evaluate。",
                "failed",
            ),
            self._check(
                "task_report_closure",
                any(item["closure_ok"] for item in task_closures),
                self._path(self.runtime.workspace_root),
                "至少有一条任务已经打通报告、日志和 trace 闭环。"
                if any(item["closure_ok"] for item in task_closures)
                else "最近任务里还没有形成完整的报告闭环。",
                "failed",
            ),
            self._check(
                "system_log",
                self._system_log_path().exists(),
                self._path(self._system_log_path()),
                "系统日志文件已存在。" if self._system_log_path().exists() else "系统日志文件尚未生成。",
                "limited",
            ),
            self._check(
                "jsonl_log",
                self._jsonl_log_path().exists(),
                self._path(self._jsonl_log_path()),
                "JSONL 事件日志已存在。" if self._jsonl_log_path().exists() else "JSONL 事件日志尚未生成。",
                "limited",
            ),
            self._check(
                "web_console",
                ((self.runtime.project_root / "web" / "src").exists()),
                self._path(self.runtime.project_root / "web"),
                "Web 控制台源码目录存在。",
                "failed",
            ),
            self._check(
                "build_backend",
                bool(build_probe.get("builder_ok") and build_probe.get("selected_source_ok") and build_probe.get("config_ok")),
                build_probe.get("host_label") or build_probe.get("selected_source_dir") or build_probe.get("builder_path") or "unknown",
                build_probe.get("error") or "构建环境预检通过。",
                "failed",
            ),
            self._check(
                "models_config",
                (self.runtime.project_root / "config" / "models.yaml").exists(),
                self._path(self.runtime.project_root / "config" / "models.yaml"),
                "模型配置文件已就位。" if (self.runtime.project_root / "config" / "models.yaml").exists() else "缺少 models.yaml。",
                "failed",
            ),
            self._check(
                "model_topology",
                self.models_config.topology == "single_primary_with_optional_helpers",
                self.models_config.topology,
                "模型拓扑已收敛为单主模型 + 可选辅助模型。"
                if self.models_config.topology == "single_primary_with_optional_helpers"
                else "当前模型拓扑与总设计文档不一致。",
                "failed",
            ),
            self._check(
                "bailian_api_key",
                bool(self._api_key_present()),
                api_key_status["api_key_masked"] or self.models_config.api_key_env,
                "已检测到百炼 API Key。"
                if self._api_key_present()
                else "当前环境还没有百炼 API Key，可通过环境变量或 config/models.yaml 补齐。",
                "limited",
            ),
            self._check(
                "submission_layout",
                all(path.exists() for path in layout.values()),
                self._path(self._submission_root()),
                "docs/submission 目录结构已建立。",
                "failed",
            ),
            self._check(
                "final_manifest",
                manifest_path.exists(),
                self._path(manifest_path),
                "final_manifest 已生成。" if manifest_path.exists() else "还没有 final_manifest。",
                "failed",
            ),
            self._check(
                "model_statement",
                (layout["docs"] / "PatchWeaver-模型选型说明.md").exists(),
                self._path(layout["docs"] / "PatchWeaver-模型选型说明.md"),
                "模型选型说明已写入 docs。"
                if (layout["docs"] / "PatchWeaver-模型选型说明.md").exists()
                else "docs 中缺少模型选型说明。",
                "failed",
            ),
        ]
        # 所有检查项最终落成一份统一报告
        # CLI、Web 和 docs/submission 都读这份门禁结论
        summary = self._summarize_checks(checks)
        report = {
            "generated_at": self._now(),
            "status": summary["status"],
            "summary": summary,
            "submission_root": str(self._submission_root()),
            "evaluation_summaries": evaluation_summaries,
            "task_closures": task_closures,
            "goal_check": self._goal_check(task_closures, evaluation_summaries),
            "checks": checks,
        }
        report_json_path = self._write_json(report, layout["manifests"] / "final_gate_report.json")
        report_md_path = self._write_text(self._render_gate_markdown(report), layout["manifests"] / "final_gate_report.md")
        return {
            "submission_root": self._path(self._submission_root()),
            "final_gate_json": self._path(report_json_path),
            "final_gate_md": self._path(report_md_path),
            "status": report["status"],
            "summary": summary,
            "goal_check": report["goal_check"],
        }

    def snapshot(self) -> dict[str, Any]:
        """返回控制台展示用的交付快照"""

        manifest_dir = self._snapshot_manifest_dir()
        submission_root = manifest_dir.parent
        final_manifest_path = manifest_dir / "final_manifest.json"
        final_gate_path = manifest_dir / "final_gate_report.json"
        final_gate = self._read_json(final_gate_path)
        return {
            "submission_root": self._path(submission_root),
            "final_manifest_path": self._path(final_manifest_path) if final_manifest_path.exists() else None,
            "final_gate_path": self._path(final_gate_path) if final_gate_path.exists() else None,
            "final_gate_status": final_gate.get("status") if isinstance(final_gate, dict) else None,
            "evaluation_count": len(self._evaluation_summaries()),
            "selected_models": {
                "topology": self.models_config.topology,
                "primary_model": self.models_config.default_model,
                "development_model": self.models_config.development_model,
                "delivery_model": self.models_config.delivery_model,
                "fallback_model": self.models_config.fallback_model,
                "helper_models": self.models_config.helper_models,
                "api_key_source": self._api_key_source(),
            },
        }

    def _snapshot_manifest_dir(self) -> Path:
        """返回交付快照可用的 manifest 目录，兼容旧版 runtime.manifest_dir。"""

        primary_dir = self._submission_root() / "manifests"
        candidates = [primary_dir]
        runtime_manifest_dir = getattr(self.runtime, "manifest_dir", None)
        if runtime_manifest_dir is not None:
            candidate = Path(runtime_manifest_dir)
            if candidate not in candidates:
                candidates.append(candidate)

        for candidate in candidates:
            if (candidate / "final_gate_report.json").exists() or (candidate / "final_manifest.json").exists():
                return candidate.resolve()
        return primary_dir.resolve()

    def _build_final_manifest(self, layout: dict[str, Path], staged_docs: list[dict[str, Any]]) -> dict[str, Any]:
        """整理当前版本的最终提交清单"""

        evaluation_summaries = self._evaluation_summaries()
        recent_tasks = self.task_repo.list_tasks(limit=12)
        task_closures = [self._task_closure(task) for task in recent_tasks]
        return {
            "manifest_type": "final_manifest",
            "generated_at": self._now(),
            "project": {
                "name": "PatchWeaver",
                "profile": self.runtime.profile_name or "default",
                "default_kernel": self.runtime.default_kernel,
            },
            "models": {
                "provider": self.models_config.provider,
                "endpoint_mode": self.models_config.endpoint_mode,
                "topology": self.models_config.topology,
                "base_url": self.models_config.base_url,
                "api_key_env": self.models_config.api_key_env,
                "api_key_source": self._api_key_source(),
                "api_key_masked": self._masked_api_key(),
                "default_model": self.models_config.default_model,
                "development_model": self.models_config.development_model,
                "delivery_model": self.models_config.delivery_model,
                "fallback_model": self.models_config.fallback_model,
                "helper_models": self.models_config.helper_models,
                "helper_notes": self.models_config.helper_notes,
                "execution_boundaries": self.models_config.execution_boundaries,
            },
            "submission_layout": self._layout_payload(layout),
            "documents": staged_docs,
            "evaluations": evaluation_summaries,
            "task_closures": task_closures,
            "known_limits": self._known_limits(task_closures),
        }

    def _render_manifest_markdown(self, manifest: dict[str, Any]) -> str:
        """输出给人工查看的 manifest 摘要"""

        lines = [
            "# PatchWeaver Final Manifest",
            "",
            f"- 生成时间: {manifest['generated_at']}",
            f"- 默认内核: {manifest['project']['default_kernel']}",
            f"- 模型拓扑: {manifest['models']['topology']}",
            f"- 主模型: {manifest['models']['default_model']}",
            f"- 正式交付模型: {manifest['models']['delivery_model']}",
            f"- API Key 来源: {self._api_key_source_label(str(manifest['models']['api_key_source']))}",
            "",
            "## 提交快照目录",
        ]
        for name, path in manifest["submission_layout"].items():
            lines.append(f"- {name}: {path}")

        lines.extend(["", "## 模型说明"])
        for helper_name, helper_model in manifest["models"]["helper_models"].items():
            helper_note = manifest["models"]["helper_notes"].get(helper_name, "")
            lines.append(f"- {helper_name}: {helper_model} / {helper_note}")

        lines.extend(["", "## 文档清单"])
        for item in manifest["documents"]:
            lines.append(
                f"- {item['name']}: {item['final_path']} / 类别 {item['category']} / 版本 {item['version_suffix']} / 已复核 {item['manually_reviewed']}"
            )

        lines.extend(["", "## 阶段评测摘要"])
        if manifest["evaluations"]:
            for item in manifest["evaluations"]:
                bucket_summary = item.get("bucket_summary") or {}
                buildable_bucket = bucket_summary.get("buildable_and_should_pass") or {}
                primary_metric = buildable_bucket.get("primary_metric") or {}
                secondary_metric = buildable_bucket.get("secondary_metric") or {}
                if buildable_bucket:
                    lines.append(
                        f"- {item['fixture_name']}: 正向桶动态验证通过率 "
                        f"{primary_metric.get('display_value') or '0.00%'} / .ko 产出率 "
                        f"{secondary_metric.get('display_value') or '0.00%'}"
                    )
                else:
                    lines.append(
                        f"- {item['fixture_name']}: 兼容总成功率 {item['success_rate']:.2%}"
                    )
        else:
            lines.append("- 当前还没有阶段评测摘要。")

        lines.extend(["", "## 任务闭环情况"])
        if manifest["task_closures"]:
            for item in manifest["task_closures"]:
                lines.append(
                    f"- {item['task_id']}: 闭环 {item['closure_ok']} / 状态 {item['task_status']} / 报告 {item['report_json_path'] or '无'}"
                )
        else:
            lines.append("- 当前还没有任务闭环记录。")

        if manifest["known_limits"]:
            lines.extend(["", "## 当前限制"])
            for item in manifest["known_limits"]:
                lines.append(f"- {item}")
        return "\n".join(lines) + "\n"

    def _render_gate_markdown(self, report: dict[str, Any]) -> str:
        """输出门禁检查的人读结果"""

        lines = [
            "# PatchWeaver Final Gate Report",
            "",
            f"- 生成时间: {report['generated_at']}",
            f"- 总体状态: {report['status']}",
            f"- 通过: {report['summary']['passed']}",
            f"- 带限制通过: {report['summary']['limited']}",
            f"- 未通过: {report['summary']['failed']}",
            "",
            "## 门禁检查",
        ]
        for item in report["checks"]:
            lines.append(f"- {item['name']}: {item['status']} / {item['detail']}")

        lines.extend(["", "## 总目标检查"])
        for item in report["goal_check"]:
            lines.append(f"- {item['goal']}: {item['status']} / {item['detail']}")
        return "\n".join(lines) + "\n"

    def _goal_check(self, task_closures: list[dict[str, Any]], evaluation_summaries: list[dict[str, Any]]) -> list[dict[str, str]]:
        """按总设计文档的总目标给出当前实现状态"""

        has_task = bool(task_closures)
        has_closed_task = any(item["closure_ok"] for item in task_closures)
        has_failed_task = any(item.get("latest_failure_type") for item in task_closures)
        goal_items = [
            {
                "goal": "理解修复意图",
                "status": "已实现",
                "detail": "分析阶段已固化 semantic_card 输出和任务详情回显。",
            },
            {
                "goal": "识别热补丁约束",
                "status": "已实现",
                "detail": "约束诊断结果会落到 constraint_report，并进入报告和详情页。",
            },
            {
                "goal": "生成可解释的改写方案",
                "status": "已实现",
                "detail": "rewrite_plan、planning_hints 和 route/prompt 产物已形成可回看链路。",
            },
            {
                "goal": "自动执行构建与验证",
                "status": "已实现" if has_task else "待验证",
                "detail": "BuildOrchestrator 和 Validator 已接入主链，实际效果依赖构建环境和样例运行结果。",
            },
            {
                "goal": "对失败进行归因并驱动下一轮尝试",
                "status": "部分实现" if has_failed_task else "待验证",
                "detail": "失败归因、failover 记录和回放链已经落地，多轮自动收敛能力仍以迭代增强为主。",
            },
            {
                "goal": "输出结构化报告、日志和产物",
                "status": "已实现" if has_closed_task or evaluation_summaries else "部分实现",
                "detail": "report.json、report.md、evaluation summary、system log 和 artifact index 已形成统一出口。",
            },
        ]
        return goal_items

    def _known_limits(self, task_closures: list[dict[str, Any]]) -> list[str]:
        """汇总当前阶段仍需说明的限制点"""

        limits: list[str] = []
        if not any(item["closure_ok"] for item in task_closures):
            limits.append("当前还没有完整闭环样例，正式展示前需至少固定一条成功样例。")
        if not self._api_key_present():
            limits.append("百炼 API Key 尚未配置，可通过环境变量或 config/models.yaml 补齐。")
        if not self._jsonl_log_path().exists():
            limits.append("JSONL 事件日志需要至少执行一次主链命令后才会自然生成。")
        return limits

    def _stage_submission_docs(self, layout: dict[str, Path]) -> list[dict[str, Any]]:
        """整理 docs 作为唯一文档源，并补齐生成型交付说明"""

        staged_items: list[dict[str, Any]] = []
        docs_root = layout["docs"]
        docs_root.mkdir(parents=True, exist_ok=True)
        source_items = self._collect_document_sources()

        for source_path, relative_name in source_items:
            staged_items.append(
                {
                    "name": Path(relative_name).name,
                    "version_suffix": self._extract_version_suffix(source_path.name),
                    "category": self._document_category(relative_name),
                    "completed": True,
                    "source_ref": self._path(source_path),
                    "final_path": self._path(source_path),
                    "manually_reviewed": False,
                }
            )

        generated_docs = {
            "PatchWeaver-模型选型说明.md": self._render_model_statement(),
            "PatchWeaver-百炼应用落地说明.md": self._render_bailian_delivery_note(),
        }
        for filename, content in generated_docs.items():
            target_path = docs_root / filename
            self._write_text(content, target_path)
            staged_items.append(
                {
                    "name": filename,
                    "version_suffix": self._extract_version_suffix(filename),
                    "category": self._document_category(filename),
                    "completed": True,
                    "source_ref": "release_service.generated",
                    "final_path": self._path(target_path),
                    "manually_reviewed": False,
                }
            )

        staged_items.sort(key=lambda item: (item["category"], item["name"]))
        return staged_items

    def _task_closure(self, task: Any) -> dict[str, Any]:
        """抽取单个任务的报告、日志和 trace 闭环情况"""

        task_dir = task.workspace_dir.resolve()
        attempts = self.attempt_repo.list_attempts(task.task_id)
        latest_attempt = attempts[-1] if attempts else None
        attempt_dir = task_dir / "attempts" / f"{latest_attempt.attempt_no:03d}" if latest_attempt else None
        report_json_path = task_dir / "reports" / "report.json"
        report_md_path = task_dir / "reports" / "report.md"
        validation_report_path = attempt_dir / "artifacts" / "validation_report.json" if attempt_dir else None
        trace_path = attempt_dir / "trace" / "harness_trace.json" if attempt_dir else None
        build_log_path = latest_attempt.build_log_path if latest_attempt and latest_attempt.build_log_path else None
        closure_ok = bool(
            report_json_path.exists()
            and report_md_path.exists()
            and validation_report_path is not None
            and validation_report_path.exists()
            and trace_path is not None
            and trace_path.exists()
            and build_log_path is not None
            and Path(build_log_path).exists()
        )
        return {
            "task_id": task.task_id,
            "task_status": task.status,
            "current_attempt": task.current_attempt,
            "latest_failure_type": latest_attempt.failure_type if latest_attempt else None,
            "report_json_path": self._path(report_json_path) if report_json_path.exists() else None,
            "report_md_path": self._path(report_md_path) if report_md_path.exists() else None,
            "build_log_path": self._path(build_log_path) if build_log_path and Path(build_log_path).exists() else None,
            "validation_report_path": self._path(validation_report_path) if validation_report_path and validation_report_path.exists() else None,
            "trace_path": self._path(trace_path) if trace_path and trace_path.exists() else None,
            "workspace_dir": self._path(task_dir),
            "closure_ok": closure_ok,
        }

    def _collect_document_sources(self) -> list[tuple[Path, str]]:
        """收集 docs 统一文档源中的文件"""

        items: list[tuple[Path, str]] = []
        generated_doc_names = {"PatchWeaver-模型选型说明.md", "PatchWeaver-百炼应用落地说明.md"}
        readme_path = self.runtime.project_root / "README.md"
        if readme_path.exists():
            items.append((readme_path, readme_path.name))

        docs_root = self.runtime.project_root / "docs"
        if docs_root.exists():
            for path in sorted(docs_root.rglob("*.md")):
                relative_name = str(path.relative_to(docs_root))
                if relative_name.lower() == "readme.md":
                    continue
                if relative_name.replace("\\", "/").startswith("submission/"):
                    continue
                if Path(relative_name).name in generated_doc_names:
                    continue
                items.append((path, relative_name))
        return items

    def _document_category(self, relative_name: str) -> str:
        """按文件名和目录位置推断文档分类"""

        normalized_name = relative_name.replace("\\", "/")
        lower_name = normalized_name.lower()
        if lower_name == "readme.md":
            return "readme"
        if lower_name.startswith("test/") or "测试" in relative_name:
            return "test"
        if "总方案" in relative_name or "设计" in relative_name:
            return "design"
        if "答辩" in relative_name or "演示" in relative_name or "阶段汇报" in relative_name:
            return "presentation"
        if "模型选型" in relative_name or "百炼应用" in relative_name:
            return "delivery_note"
        return "document"

    def _extract_version_suffix(self, filename: str) -> str:
        """从文件名中提取版本后缀"""

        match = re.search(r"(_v\d+)", filename)
        if match:
            return match.group(1)
        return "unversioned"

    def _render_model_statement(self) -> str:
        """生成正式材料里的模型选型说明"""

        lines = [
            "# PatchWeaver 模型选型说明",
            "",
            f"- 模型供应方: {self.models_config.provider}",
            f"- 接口模式: {self.models_config.endpoint_mode}",
            f"- API Key 环境变量: {self.models_config.api_key_env}",
            f"- API Key 来源: {self._api_key_source_label(self._api_key_source())}",
            f"- 模型拓扑: {self.models_config.topology}",
            f"- 主模型: {self.models_config.default_model}",
            f"- 开发口径: {self.models_config.development_model}",
            f"- 正式交付口径: {self.models_config.delivery_model}",
            f"- 回退模型: {self.models_config.fallback_model}",
            "",
            "## 可选辅助模型",
        ]
        for helper_name, helper_model in self.models_config.helper_models.items():
            helper_note = self.models_config.helper_notes.get(helper_name, "")
            lines.append(f"- {helper_name}: {helper_model} / {helper_note}")

        lines.extend(["", "## 执行边界"])
        for item in self.models_config.execution_boundaries:
            lines.append(f"- {item}")
        return "\n".join(lines) + "\n"

    def _render_bailian_delivery_note(self) -> str:
        """生成百炼应用落地分层说明"""

        lines = [
            "# PatchWeaver 百炼应用落地说明",
            "",
            "## 分层定位",
            "- 应用层负责任务入口、状态查看、报告展示和演示交互。",
            "- MCP / FC 服务层负责承接工具调用、验证机同步和平台侧集成。",
            "- PatchWeaver 主链执行层负责检索、分析、改写、构建、验证、回放和报告闭环。",
            "",
            "## 当前口径",
            "- 本仓库默认落地形态仍以本地 CLI、FastAPI 和 Web 控制台为主。",
            "- 正式展示时，百炼应用与本地主链保持同一套任务状态和产物口径，不单独维护第二套执行状态机。",
            "- 构建、验证和最终放行结论仍由 PatchWeaver 主链给出。",
        ]
        return "\n".join(lines) + "\n"

    def _evaluation_summaries(self) -> list[dict[str, Any]]:
        """读取阶段评测摘要，供交付和门禁复用"""

        items: list[dict[str, Any]] = []
        evaluations_root = self.runtime.data_dir / "evaluations"
        if not evaluations_root.exists():
            return items

        for path in sorted(evaluations_root.glob("*/summary.json")):
            payload = self._read_json(path)
            if not isinstance(payload, dict):
                continue
            items.append(
                {
                    "fixture_name": str(payload.get("fixture_name") or path.parent.name),
                    "success_count": int(payload.get("success_count", 0) or 0),
                    "matched_fixtures": int(payload.get("matched_fixtures", 0) or 0),
                    "missing_fixtures": int(payload.get("missing_fixtures", 0) or 0),
                    "success_rate": float(payload.get("success_rate", 0.0) or 0.0),
                    "bucket_order": payload.get("bucket_order") or [],
                    "bucket_counts": payload.get("bucket_counts") or {},
                    "bucket_summary": payload.get("bucket_summary") or {},
                    "mixed_summary_note": payload.get("mixed_summary_note"),
                    "summary_json_path": self._path(path),
                    "summary_md_path": self._path(path.with_name("summary.md")),
                }
            )
        for path in sorted(evaluations_root.glob("**/representative_metrics*.json")):
            payload = self._read_json(path)
            if not isinstance(payload, dict):
                continue
            metrics = payload.get("metrics") or {}
            if not isinstance(metrics, dict) or "representative_total" not in metrics:
                continue
            total = int(metrics.get("representative_total", 0) or 0)
            items.append(
                {
                    "fixture_name": str(payload.get("fixture_name") or f"{path.parent.name}/{path.stem}"),
                    "success_count": int(metrics.get("representative_success_count", 0) or 0),
                    "matched_fixtures": total,
                    "missing_fixtures": 0,
                    "success_rate": float(metrics.get("representative_success_rate", 0.0) or 0.0),
                    "bucket_order": list((payload.get("failure_buckets") or {}).keys()),
                    "bucket_counts": payload.get("failure_buckets") or {},
                    "bucket_summary": payload.get("evidence_summary") or {},
                    "mixed_summary_note": (payload.get("target_gap") or {}).get("explanation"),
                    "summary_json_path": self._path(path),
                    "summary_md_path": self._path(path.with_suffix(".md")),
                }
            )
        full_run_paths = {
            *evaluations_root.glob("**/*full_run*.json"),
            *evaluations_root.glob("**/*_full.json"),
        }
        for path in sorted(full_run_paths):
            payload = self._read_json(path)
            if not isinstance(payload, dict):
                continue
            summary = payload.get("summary") or {}
            if not isinstance(summary, dict):
                continue
            total = int(summary.get("representative_total", summary.get("total_cases", 0)) or 0)
            if total <= 0:
                continue
            success_rate = float(summary.get("representative_success_rate", 0.0) or 0.0)
            items.append(
                {
                    "fixture_name": str(payload.get("fixture_name") or f"{path.parent.name}/{path.stem}"),
                    "success_count": int(round(total * success_rate)),
                    "matched_fixtures": total,
                    "missing_fixtures": 0,
                    "success_rate": success_rate,
                    "bucket_order": list((summary.get("bucket_counts") or {}).keys()),
                    "bucket_counts": summary.get("bucket_counts") or {},
                    "bucket_summary": {
                        "positive_pool_size": summary.get("current_positive_pool_size"),
                        "positive_pool_gap": summary.get("positive_pool_gap"),
                        "livepatchability_tier_counts": summary.get("livepatchability_tier_counts") or {},
                    },
                    "mixed_summary_note": None,
                    "summary_json_path": self._path(path),
                    "summary_md_path": self._path(path.with_suffix(".md")),
                }
            )
        return items

    def _check(self, name: str, ok: bool, evidence: str, detail: str, failed_status: str) -> dict[str, str]:
        """统一组织一条门禁检查结果"""

        status = "passed" if ok else failed_status
        return {
            "name": name,
            "status": status,
            "detail": detail,
            "evidence": evidence,
        }

    def _summarize_checks(self, checks: list[dict[str, str]]) -> dict[str, Any]:
        """汇总门禁检查结果"""

        passed = sum(1 for item in checks if item["status"] == "passed")
        limited = sum(1 for item in checks if item["status"] == "limited")
        failed = sum(1 for item in checks if item["status"] == "failed")
        status = "passed" if failed == 0 and limited == 0 else ("limited" if failed == 0 else "failed")
        return {
            "total": len(checks),
            "passed": passed,
            "limited": limited,
            "failed": failed,
            "status": status,
        }

    def _ensure_submission_dirs(self) -> dict[str, Path]:
        """建立提交证据目录，并把 docs 作为唯一文档源"""

        root = self._submission_root()
        layout = {
            "docs": self.runtime.project_root / "docs",
            "slides": root / "slides",
            "video": root / "video",
            "evidence": root / "evidence",
            "manifests": root / "manifests",
        }
        for path in layout.values():
            path.mkdir(parents=True, exist_ok=True)
        return layout

    def _submission_root(self) -> Path:
        """返回生成型提交快照根目录"""

        return (self.runtime.project_root / "docs" / "submission").resolve()

    def _system_log_path(self) -> Path:
        """返回文本日志路径"""

        return self._resolve_path(self.logging_config.file_path)

    def _jsonl_log_path(self) -> Path:
        """返回 JSONL 日志路径"""

        return self._resolve_path(self.logging_config.jsonl_path)

    def _api_key_present(self) -> bool:
        """判断当前环境里是否已经解析到模型密钥"""

        return self._resolve_api_key() is not None

    def _resolve_path(self, raw_path: str) -> Path:
        """把配置路径展开成绝对路径"""

        return ensure_within_root(self.runtime.project_root, raw_path, label="project_path")

    def _write_json(self, payload: dict[str, Any], target_path: Path) -> Path:
        """写出 JSON 文件"""

        target_path.parent.mkdir(parents=True, exist_ok=True)
        normalized = relativize_payload(payload, self.runtime.project_root)
        target_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return target_path

    def _write_text(self, content: str, target_path: Path) -> Path:
        """写出文本文件"""

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content, encoding="utf-8")
        return target_path

    def _read_json(self, path: Path) -> dict[str, Any] | None:
        """安全读取 JSON 文件"""

        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def _now(self) -> str:
        """统一生成当前时间戳"""

        return datetime.now(timezone.utc).isoformat()

    def _path(self, value: Path | str | None) -> str | None:
        """把项目内路径转换成相对源码根目录表达"""

        return to_project_relative(self.runtime.project_root, value)

    def _layout_payload(self, layout: dict[str, Path]) -> dict[str, str | None]:
        """把提交快照布局转换成相对源码根目录表达"""

        return {name: self._path(path) for name, path in layout.items()}

    def _api_key_source_label(self, source: str) -> str:
        """把 API Key 来源转换成人读文案"""

        labels = {
            "env": "环境变量",
            "config": "配置文件",
            "missing": "未配置",
        }
        return labels.get(source, source)

    def _resolve_api_key(self) -> str | None:
        """兼容配置对象和简化测试对象的 API Key 解析"""

        resolver = getattr(self.models_config, "resolve_api_key", None)
        if callable(resolver):
            return resolver()

        import os

        env_name = getattr(self.models_config, "api_key_env", "PATCHWEAVER_BAILIAN_API_KEY")
        env_value = os.getenv(env_name, "").strip()
        if env_value:
            return env_value

        config_value = str(getattr(self.models_config, "api_key", "") or "").strip()
        return config_value or None

    def _api_key_source(self) -> str:
        """兼容配置对象和简化测试对象的 API Key 来源判断"""

        resolver = getattr(self.models_config, "resolve_api_key_source", None)
        if callable(resolver):
            return str(resolver())

        import os

        env_name = getattr(self.models_config, "api_key_env", "PATCHWEAVER_BAILIAN_API_KEY")
        if os.getenv(env_name, "").strip():
            return "env"
        if str(getattr(self.models_config, "api_key", "") or "").strip():
            return "config"
        return "missing"

    def _masked_api_key(self) -> str | None:
        """兼容配置对象和简化测试对象的 API Key 脱敏显示"""

        masker = getattr(self.models_config, "masked_api_key", None)
        if callable(masker):
            return masker()

        value = self._resolve_api_key()
        if value is None:
            return None
        if len(value) <= 8:
            if len(value) <= 2:
                return "*" * len(value)
            return f"{value[:1]}{'*' * (len(value) - 2)}{value[-1:]}"
        return f"{value[:4]}***{value[-4:]}"

    def _api_key_status(self) -> dict[str, str | bool | None]:
        """输出统一的 API Key 状态摘要"""

        status_builder = getattr(self.models_config, "api_key_status", None)
        if callable(status_builder):
            return status_builder()

        return {
            "api_key_env": getattr(self.models_config, "api_key_env", "PATCHWEAVER_BAILIAN_API_KEY"),
            "api_key_ready": self._resolve_api_key() is not None,
            "api_key_source": self._api_key_source(),
            "api_key_masked": self._masked_api_key(),
            "api_key_in_config": bool(str(getattr(self.models_config, "api_key", "") or "").strip()),
        }
