"""报告生成骨架"""

from __future__ import annotations

from pathlib import Path

from patchweaver.models.attempt import AttemptRecord
from patchweaver.models.harness import ArtifactRef
from patchweaver.models.report import AttemptDigest, FinalReport
from patchweaver.models.task import TaskContext
from patchweaver.models.validation import ValidationReport
from patchweaver.utils.path_policy import to_project_relative


class ReportBuilder:
    """负责汇总任务结果并生成最终报告"""

    def __init__(self, project_root: Path | None = None) -> None:
        """保存项目根目录，供报告路径输出使用"""

        self.project_root = project_root.resolve() if project_root is not None else None

    def _next_step(self, *, attempts: list[AttemptRecord], closure_summary: dict[str, object]) -> tuple[str | None, str | None]:
        """根据最新尝试结果给出下一轮优先修复层和动作建议"""

        if not attempts:
            return None, None

        latest = attempts[-1]
        if latest.status in {"created", "running"}:
            return "execution", "当前尝试尚未结束，先补齐构建、归因和验证阶段产物"
        if bool(closure_summary.get("success_replay_ready")):
            return "freeze", "当前任务已具备成功回放闭环，优先固化样例、脚本和验收材料"
        if latest.status == "built":
            return "validation", "继续补齐验证证据，形成成功放行后的回放闭环"

        mapping: dict[str, tuple[str, str]] = {
            "build_env_missing": ("build_env", "补齐 kpatch-build、git 等构建依赖后重试"),
            "kernel_src_missing": ("source_tree", "补齐可用于 apply 和构建的完整内核源码树"),
            "kernel_config_missing": ("build_env", "补齐 .config 后重新执行预检查"),
            "vmlinux_missing": ("build_env", "补齐 vmlinux 调试符号文件后重试"),
            "patch_apply_failed": ("patch_apply", "优先检查补丁上下文与目标源码差异，必要时补 backport 改写"),
            "target_already_patched": ("target_state", "目标源码已包含修复；请切换未修复内核、调整样例或显式识别已修复状态"),
            "feature_not_enabled": ("kernel_profile", "当前验证内核未启用目标子系统；请切换内核配置或更换样例"),
            "compile_failed": ("compile", "分析编译报错并收缩改写范围"),
            "kpatch_constraint": ("kpatch_constraint", "根据 kpatch 约束调整原语和改写策略"),
        }
        return mapping.get(
            latest.failure_type or "",
            ("failure_analysis", "继续补充失败归因信息，明确下一轮优先修改层"),
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
        validation_report = self._load_validation_report(artifact_lookup.get("validation_report"))
        closure_summary = self._build_closure_summary(
            latest_attempt=latest_attempt,
            artifact_lookup=artifact_lookup,
            validation_report=validation_report,
        )
        next_priority_layer, next_action = self._next_step(attempts=attempts, closure_summary=closure_summary)
        known_limits = self._build_known_limits(
            latest_attempt=latest_attempt,
            closure_summary=closure_summary,
        )

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
                "build_log_path": self._path(latest_attempt.build_log_path)
                if latest_attempt and latest_attempt.build_log_path
                else artifact_lookup.get("build_log"),
                "module_path": self._path(latest_attempt.module_path)
                if latest_attempt and latest_attempt.module_path
                else None,
                "rewritten_patch_path": self._path(latest_attempt.rewritten_patch_path)
                if latest_attempt and latest_attempt.rewritten_patch_path
                else artifact_lookup.get("rewritten_patch"),
            },
            validation_summary=self._build_validation_summary(
                artifact_lookup=artifact_lookup,
                validation_report=validation_report,
            ),
            closure_summary=closure_summary,
            replay_summary={
                "trace_path": artifact_lookup.get("harness_trace"),
                "failover_record_path": artifact_lookup.get("failover_record"),
                "evaluation_summary_path": artifact_lookup.get("evaluation_summary"),
                "recommended_replay_files": closure_summary["recommended_replay_files"],
            },
            key_paths={
                "report_json": artifact_lookup.get("final_report_json"),
                "report_md": artifact_lookup.get("final_report_md"),
                "workspace_dir": self._path(task.workspace_dir),
                "report_trace": artifact_lookup.get("harness_trace"),
                "report_build_log": self._path(latest_attempt.build_log_path)
                if latest_attempt and latest_attempt.build_log_path
                else artifact_lookup.get("build_log"),
            },
            known_limits=known_limits,
            explanations=explanations or [],
            next_priority_layer=next_priority_layer,
            next_action=next_action,
        )

    def _build_known_limits(
        self,
        *,
        latest_attempt: AttemptRecord | None,
        closure_summary: dict[str, object],
    ) -> list[str]:
        """整理当前报告仍需说明的限制点"""

        known_limits: list[str] = []
        if latest_attempt is None:
            known_limits.append("当前还没有尝试轮记录，报告只包含任务骨架")
            return known_limits

        if latest_attempt.status in {"created", "running"}:
            known_limits.append(f"最近一轮状态为 {latest_attempt.status}，该尝试尚未形成最终构建结论")
        elif latest_attempt.status == "failed":
            known_limits.append(f"最近一轮失败类型为 {latest_attempt.failure_type or 'unknown'}，仍需结合回放进一步排查")
        elif latest_attempt.target_state == "target_already_patched":
            known_limits.append("最近一轮目标源码已包含修复，真实构建未执行，也未生成新的 .ko 产物")

        for item in closure_summary.get("missing_success_evidence", []):
            known_limits.append(f"成功回放证据缺口: {item}")
        return known_limits

    def _build_validation_summary(
        self,
        *,
        artifact_lookup: dict[str, str],
        validation_report: ValidationReport | None,
    ) -> dict[str, object]:
        """整理验证摘要，供报告直接展示"""

        summary = {
            "validation_report_path": artifact_lookup.get("validation_report"),
            "validation_matrix_path": artifact_lookup.get("validation_matrix"),
            "semantic_guard_path": artifact_lookup.get("semantic_guard"),
        }
        if validation_report is None:
            summary["validation_status"] = None
            summary["validation_intensity"] = None
            return summary

        summary["validation_status"] = validation_report.status
        summary["validation_intensity"] = validation_report.validation_intensity
        summary["semantic_guard_status"] = validation_report.semantic_guard_result.status
        summary["load_status"] = validation_report.load_result.status
        summary["unload_status"] = validation_report.unload_result.status
        summary["smoke_status"] = validation_report.smoke_result.status
        summary["selftest_status"] = validation_report.selftest_result.status
        summary["regression_status"] = validation_report.regression_result.status
        return summary

    def _build_closure_summary(
        self,
        *,
        latest_attempt: AttemptRecord | None,
        artifact_lookup: dict[str, str],
        validation_report: ValidationReport | None,
    ) -> dict[str, object]:
        """判断当前任务属于哪类回放闭环"""

        if latest_attempt is None:
            return {
                "closure_type": "pending",
                "closure_status": "missing_attempt",
                "failure_replay_ready": False,
                "success_replay_ready": False,
                "missing_success_evidence": ["缺少尝试轮记录"],
                "recommended_replay_files": [],
            }

        validation_status = validation_report.status if validation_report is not None else None
        missing_success_evidence = (
            self._missing_success_evidence(
                latest_attempt=latest_attempt,
                artifact_lookup=artifact_lookup,
                validation_report=validation_report,
            )
            if latest_attempt.status == "built"
            else []
        )
        failure_replay_ready = latest_attempt.status in {"failed", "target_state"} and bool(
            artifact_lookup.get("failure_record") and artifact_lookup.get("harness_trace")
        )
        success_replay_ready = latest_attempt.status == "built" and not missing_success_evidence

        if success_replay_ready:
            closure_type = "success"
            closure_status = "ready"
        elif latest_attempt.status == "built":
            closure_type = "success_pending"
            closure_status = "missing_success_evidence"
        elif failure_replay_ready:
            closure_type = "failure"
            closure_status = "ready"
        else:
            closure_type = "partial"
            closure_status = "incomplete"

        return {
            "closure_type": closure_type,
            "closure_status": closure_status,
            "failure_replay_ready": failure_replay_ready,
            "success_replay_ready": success_replay_ready,
            "validation_status": validation_status,
            "missing_success_evidence": missing_success_evidence,
            "recommended_replay_files": self._recommended_replay_files(
                latest_attempt=latest_attempt,
                artifact_lookup=artifact_lookup,
                success_replay_ready=success_replay_ready,
            ),
        }

    def _missing_success_evidence(
        self,
        *,
        latest_attempt: AttemptRecord,
        artifact_lookup: dict[str, str],
        validation_report: ValidationReport | None,
    ) -> list[str]:
        """判断成功回放还缺哪些关键证据"""

        missing: list[str] = []
        if latest_attempt.status != "built":
            missing.append("最近一轮尚未成功构建")
            return missing

        if latest_attempt.build_exec_status != "executed":
            missing.append("最近一轮未形成真实构建执行记录")
        if latest_attempt.module_path is None:
            missing.append("缺少模块产物路径")
        if artifact_lookup.get("harness_trace") is None:
            missing.append("缺少 harness_trace")
        if artifact_lookup.get("rewritten_patch") is None:
            missing.append("缺少 rewritten_patch")
        if artifact_lookup.get("build_log") is None:
            missing.append("缺少 build_log")
        if artifact_lookup.get("validation_report") is None or validation_report is None:
            missing.append("缺少 validation_report")
            return missing
        if validation_report.status != "passed":
            missing.append(f"验证结果尚未放行，当前状态为 {validation_report.status}")
        if artifact_lookup.get("validation_matrix") is None:
            missing.append("缺少 validation_matrix")
        for artifact_type in ["selftest_log", "load_log", "unload_log", "smoke_log"]:
            if artifact_lookup.get(artifact_type) is None:
                missing.append(f"缺少 {artifact_type}")
        return missing

    def _recommended_replay_files(
        self,
        *,
        latest_attempt: AttemptRecord,
        artifact_lookup: dict[str, str],
        success_replay_ready: bool,
    ) -> list[str]:
        """根据当前闭环类型整理建议查看的文件"""

        ordered_types = (
            [
                "harness_trace",
                "rewritten_patch",
                "build_log",
                "validation_report",
                "validation_matrix",
                "selftest_log",
                "load_log",
                "unload_log",
                "smoke_log",
                "regression_log",
            ]
            if success_replay_ready
            else [
                "harness_trace",
                "failure_record",
                "build_log",
                "validation_report",
                "failover_record",
            ]
        )
        results: list[str] = []
        for artifact_type in ordered_types:
            path = artifact_lookup.get(artifact_type)
            if path is None:
                continue
            results.append(path)
        if latest_attempt.build_log_path is not None:
            build_log_path = self._path(latest_attempt.build_log_path)
            if build_log_path is not None and build_log_path not in results:
                results.append(build_log_path)
        return results

    def _load_validation_report(self, raw_path: str | None) -> ValidationReport | None:
        """读取当前任务最新的验证报告"""

        if raw_path is None:
            return None
        path = self._absolute_path(raw_path)
        if path is None or not path.exists():
            return None
        try:
            return ValidationReport.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:
            # 历史任务里可能只留下半成品 JSON，报告阶段不能因为这个中断
            return None

    def _artifact_lookup(self, artifacts: list[ArtifactRef]) -> dict[str, str]:
        """把同类产物整理成最后一次出现的路径"""

        lookup: dict[str, str] = {}
        for artifact in artifacts:
            lookup[artifact.artifact_type] = self._path(artifact.artifact_path)
        return lookup

    def _absolute_path(self, raw_path: str | None) -> Path | None:
        """把相对源码根目录的路径还原成绝对路径"""

        if raw_path is None:
            return None
        path = Path(raw_path)
        if path.is_absolute():
            return path
        if self.project_root is None:
            return None
        return self.project_root / path

    def _path(self, value: Path | None) -> str | None:
        """把路径统一转换成相对源码根目录的表示"""

        return to_project_relative(self.project_root, value)
