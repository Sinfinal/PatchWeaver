"""报告生成骨架"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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
            "target_arch_mismatch": ("kernel_profile", "补丁目标架构与当前验证内核不一致；请切换目标架构或从正向池剔除"),
            "build_cache_incomplete": ("build_env", "prepared source tree 构建缓存不完整；请预热 vmlinux 或同步完整缓存"),
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
            agent_decision_summary=self._build_agent_decision_summary(
                task=task,
                latest_attempt=latest_attempt,
                artifact_lookup=artifact_lookup,
            ),
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

    def _build_agent_decision_summary(
        self,
        *,
        task: TaskContext,
        latest_attempt: AttemptRecord | None,
        artifact_lookup: dict[str, str],
    ) -> dict[str, object]:
        """Surface repair intent, selected strategy, and failure attribution in reports."""

        attempt_dir = task.workspace_dir / "attempts" / f"{latest_attempt.attempt_no:03d}" if latest_attempt else None
        repair_intent_path = self._artifact_or_default(
            artifact_lookup,
            "repair_intent",
            task.workspace_dir / "analysis" / "repair_intent.json",
        )
        if repair_intent_path is not None and not repair_intent_path.exists() and attempt_dir is not None:
            fallback = attempt_dir / "artifacts" / "repair_intent.json"
            if fallback.exists():
                repair_intent_path = fallback
        rewrite_plan_path = self._artifact_or_default(
            artifact_lookup,
            "rewrite_plan",
            attempt_dir / "rewrite" / "rewrite_plan.json" if attempt_dir else None,
        )
        failure_record_path = self._artifact_or_default(
            artifact_lookup,
            "failure_record",
            attempt_dir / "logs" / "failure_record.json" if attempt_dir else None,
        )
        build_summary_path = self._artifact_or_default(
            artifact_lookup,
            "build_summary",
            attempt_dir / "artifacts" / "build_summary.json" if attempt_dir else None,
        )

        repair_intent = self._read_json_payload(repair_intent_path)
        rewrite_plan = self._read_json_payload(rewrite_plan_path)
        failure_record = self._read_json_payload(failure_record_path)
        build_summary = self._read_json_payload(build_summary_path)

        intent_strategy = self._first_present(
            repair_intent,
            keys=("recommended_strategy", "repair_strategy", "strategy"),
        )
        selected_recipe = self._first_present(
            rewrite_plan,
            build_summary,
            keys=("selected_recipe", "recipe", "recipe_name"),
        )
        selected_strategy = self._first_present(
            rewrite_plan,
            build_summary,
            keys=("selected_strategy", "strategy", "route", "rewrite_strategy"),
        )
        final_strategy = selected_strategy or selected_recipe or intent_strategy
        failure_type = self._first_present(
            build_summary,
            failure_record,
            keys=("failure_type", "expected_failure_type"),
        ) or (latest_attempt.failure_type if latest_attempt else None)
        diagnostic_details = self._first_present(
            failure_record,
            build_summary,
            keys=("diagnostic_details", "diagnostics", "details", "root_cause_details"),
        )
        strategy_switched = bool(
            intent_strategy
            and final_strategy
            and str(intent_strategy) not in {str(final_strategy), str(selected_recipe)}
        )

        return {
            "repair_intent": self._repair_intent_summary(repair_intent, task=task),
            "selected_recipe": selected_recipe,
            "selected_strategy": selected_strategy,
            "strategy": final_strategy,
            "strategy_switch": {
                "repair_intent_strategy": intent_strategy,
                "selected_recipe": selected_recipe,
                "selected_strategy": selected_strategy,
                "final_strategy": final_strategy,
                "switched": strategy_switched,
                "reason": self._first_present(
                    rewrite_plan,
                    build_summary,
                    keys=("selection_reason", "strategy_reason", "reason"),
                ),
            },
            "failure_type": failure_type,
            "failure_attribution": {
                "present": bool(failure_type or failure_record),
                "stage_name": (failure_record or {}).get("stage_name"),
                "failure_type": failure_type,
                "summary": self._first_present(failure_record, build_summary, keys=("summary",)),
                "agent_next_action": self._first_present(
                    failure_record,
                    build_summary,
                    keys=("agent_next_action", "next_action", "recommended_action"),
                ),
                "diagnostic_details": diagnostic_details,
            },
            "source_paths": {
                "repair_intent": self._path(repair_intent_path),
                "rewrite_plan": self._path(rewrite_plan_path),
                "failure_record": self._path(failure_record_path),
                "build_summary": self._path(build_summary_path),
            },
            "source_exists": {
                "repair_intent": bool(repair_intent_path and repair_intent_path.exists()),
                "rewrite_plan": bool(rewrite_plan_path and rewrite_plan_path.exists()),
                "failure_record": bool(failure_record_path and failure_record_path.exists()),
                "build_summary": bool(build_summary_path and build_summary_path.exists()),
            },
        }

    def _repair_intent_summary(self, payload: dict[str, Any] | None, *, task: TaskContext) -> dict[str, Any] | None:
        """Reduce RepairIntent to the fields expected in reports and UI payloads."""

        if payload is None:
            return None
        return {
            "present": True,
            "cve_id": payload.get("cve_id") or task.cve_id,
            "bug_class": payload.get("bug_class"),
            "root_cause": payload.get("root_cause"),
            "vulnerability_conditions": payload.get("vulnerability_conditions") or [],
            "guard_conditions": payload.get("guard_conditions") or [],
            "guard_sites": payload.get("guard_sites") or [],
            "safe_exits": payload.get("safe_exits") or [],
            "preserved_side_effects": payload.get("preserved_side_effects") or [],
            "touched_files": payload.get("touched_files") or [],
            "touched_functions": payload.get("touched_functions") or [],
            "touched_state": payload.get("touched_state") or [],
            "recommended_strategy": payload.get("recommended_strategy"),
            "confidence": payload.get("confidence"),
            "evidence": payload.get("evidence") or [],
        }

    def _artifact_or_default(
        self,
        artifact_lookup: dict[str, str],
        artifact_type: str,
        default_path: Path | None,
    ) -> Path | None:
        """Resolve a registered artifact path, falling back to the canonical workspace path."""

        raw_path = artifact_lookup.get(artifact_type)
        if raw_path:
            path = self._absolute_path(raw_path)
            if path is not None:
                return path
        return default_path

    def _read_json_payload(self, path: Path | None) -> dict[str, Any] | None:
        """Read a JSON object without failing report generation."""

        if path is None or not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _first_present(self, *sources: dict[str, Any] | None, keys: tuple[str, ...]) -> Any | None:
        """Return the first non-empty value from ordered JSON payloads."""

        for source in sources:
            if not isinstance(source, dict):
                continue
            for key in keys:
                value = source.get(key)
                if value not in (None, "", [], {}):
                    return value
        return None

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
