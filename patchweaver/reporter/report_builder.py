"""报告生成骨架"""

from __future__ import annotations

from pathlib import Path

from patchweaver.models.harness import ArtifactRef
from patchweaver.models.report import AttemptDigest, FinalReport
from patchweaver.models.task import TaskContext
from patchweaver.models.attempt import AttemptRecord
from patchweaver.utils.path_policy import to_project_relative


class ReportBuilder:
    """负责汇总任务结果并生成最终报告"""

    def __init__(self, project_root: Path | None = None) -> None:
        """保存项目根目录，供报告路径输出使用"""

        self.project_root = project_root.resolve() if project_root is not None else None

    def _next_step(self, *, attempts: list[AttemptRecord]) -> tuple[str | None, str | None]:
        """根据最新尝试结果给出下一轮优先修复层和动作建议"""

        if not attempts:
            return None, None

        latest = attempts[-1]
        if latest.status in {"created", "running"}:
            return "execution", "当前尝试尚未结束，先补齐构建、归因和验证阶段产物。"
        if latest.status == "built":
            return "validation", "继续执行加载、卸载、smoke 和 selftest，补齐最小验证闭环。"

        mapping: dict[str, tuple[str, str]] = {
            "build_env_missing": ("build_env", "补齐 kpatch-build、git 等构建依赖后重试。"),
            "kernel_src_missing": ("source_tree", "补齐可用于 apply 和构建的完整内核源码树。"),
            "kernel_config_missing": ("build_env", "补齐 .config 后重新执行预检查。"),
            "vmlinux_missing": ("build_env", "补齐 vmlinux 调试符号文件后重试。"),
            "patch_apply_failed": ("patch_apply", "优先检查补丁上下文与目标源码差异，必要时补 backport 改写。"),
            "target_already_patched": ("target_state", "目标源码已包含修复；请切换未修复内核、调整样例或显式识别已修复状态。"),
            "compile_failed": ("compile", "分析编译报错并收缩改写范围。"),
            "kpatch_constraint": ("kpatch_constraint", "根据 kpatch 约束调整原语和改写策略。"),
        }
        return mapping.get(
            latest.failure_type or "",
            ("failure_analysis", "继续补充失败归因信息，明确下一轮优先修改层。"),
        )

    def build_report(
        self,
        *,
        task: TaskContext,
        attempts: list[AttemptRecord],
        artifacts: list[ArtifactRef],
        evaluation_summary: dict[str, object] | None = None,
        explanations: list[str] | None = None,
    ) -> FinalReport:
        """根据任务、尝试和产物索引生成报告"""

        artifact_lookup = self._artifact_lookup(artifacts)
        latest_attempt = attempts[-1] if attempts else None
        next_priority_layer, next_action = self._next_step(attempts=attempts)
        known_limits: list[str] = []
        if latest_attempt is None:
            known_limits.append("当前还没有尝试轮记录，报告只包含任务骨架。")
        elif latest_attempt.status in {"created", "running"}:
            known_limits.append(f"最近一轮状态为 {latest_attempt.status}，该尝试尚未形成最终构建结论。")
        elif latest_attempt.status == "failed":
            known_limits.append(f"最近一轮失败类型为 {latest_attempt.failure_type or 'unknown'}，仍需结合回放进一步排查。")
        elif latest_attempt.target_state == "target_already_patched":
            known_limits.append("最近一轮目标源码已包含修复，真实构建未执行，也未生成新的 .ko 产物。")

        return FinalReport(
            task_summary={
                "task_id": task.task_id,
                "cve_id": task.cve_id,
                "target_kernel": task.target_kernel,
                "profile_name": task.profile_name or "default",
                "workspace_dir": self._path(task.workspace_dir),
            },
            attempt_digest=[
                AttemptDigest(
                    attempt_id=item.attempt_id,
                    attempt_no=item.attempt_no,
                    status=item.status,
                    failure_type=item.failure_type,
                    build_exec_status=item.build_exec_status,
                    target_state=item.target_state,
                )
                for item in attempts
            ],
            artifact_index=artifacts,
            final_status=task.status,
            evaluation_summary=evaluation_summary or {},
            analysis_summary={
                "semantic_card_path": artifact_lookup.get("semantic_card"),
                "constraint_report_path": artifact_lookup.get("constraint_report"),
                "patch_bundle_path": artifact_lookup.get("patch_bundle"),
            },
            build_summary={
                "latest_attempt_id": latest_attempt.attempt_id if latest_attempt else None,
                "latest_attempt_status": latest_attempt.status if latest_attempt else None,
                "latest_failure_type": latest_attempt.failure_type if latest_attempt else None,
                "latest_build_exec_status": latest_attempt.build_exec_status if latest_attempt else None,
                "latest_target_state": latest_attempt.target_state if latest_attempt else None,
                "build_log_path": self._path(latest_attempt.build_log_path) if latest_attempt and latest_attempt.build_log_path else artifact_lookup.get("build_log"),
                "module_path": self._path(latest_attempt.module_path) if latest_attempt and latest_attempt.module_path else None,
                "rewritten_patch_path": self._path(latest_attempt.rewritten_patch_path) if latest_attempt and latest_attempt.rewritten_patch_path else artifact_lookup.get("rewritten_patch"),
            },
            validation_summary={
                "validation_report_path": artifact_lookup.get("validation_report"),
                "validation_matrix_path": artifact_lookup.get("validation_matrix"),
                "semantic_guard_path": artifact_lookup.get("semantic_guard"),
            },
            replay_summary={
                "trace_path": artifact_lookup.get("harness_trace"),
                "failover_record_path": artifact_lookup.get("failover_record"),
                "evaluation_summary_path": artifact_lookup.get("evaluation_summary"),
            },
            key_paths={
                "report_json": artifact_lookup.get("final_report_json"),
                "report_md": artifact_lookup.get("final_report_md"),
                "workspace_dir": self._path(task.workspace_dir),
                "report_trace": artifact_lookup.get("harness_trace"),
                "report_build_log": self._path(latest_attempt.build_log_path) if latest_attempt and latest_attempt.build_log_path else artifact_lookup.get("build_log"),
            },
            known_limits=known_limits,
            explanations=explanations or [],
            next_priority_layer=next_priority_layer,
            next_action=next_action,
        )

    def _artifact_lookup(self, artifacts: list[ArtifactRef]) -> dict[str, str]:
        """把同类产物整理成最后一次出现的路径"""

        lookup: dict[str, str] = {}
        for artifact in artifacts:
            lookup[artifact.artifact_type] = self._path(artifact.artifact_path)
        return lookup

    def _path(self, value: Path | None) -> str | None:
        """把路径统一转换成相对源码根目录的表示"""

        return to_project_relative(self.project_root, value)
