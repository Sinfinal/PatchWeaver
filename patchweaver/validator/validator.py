"""验证编排器"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from patchweaver.models.attempt import AttemptRecord, BuildSummary
from patchweaver.models.constraint import ConstraintReport
from patchweaver.models.task import TaskContext
from patchweaver.models.validation import ValidationItem, ValidationMatrixEntry, ValidationReport
from patchweaver.validator.load_tester import LoadTester
from patchweaver.validator.regression_tester import RegressionTester
from patchweaver.validator.semantic_guard import SemanticGuard
from patchweaver.validator.semantic_precheck import SemanticPrecheck
from patchweaver.validator.selftest_runner import SelftestRunner
from patchweaver.validator.smoke_tester import SmokeTester


class Validator:
    """负责组织静态检查、动态验证和语义守卫"""

    def __init__(
        self,
        *,
        verify_config: Any | None = None,
        build_config: Any | None = None,
        project_root: Path | None = None,
        semantic_precheck: SemanticPrecheck | None = None,
        semantic_guard: SemanticGuard | None = None,
        load_tester: LoadTester | None = None,
        smoke_tester: SmokeTester | None = None,
        regression_tester: RegressionTester | None = None,
        selftest_runner: SelftestRunner | None = None,
    ) -> None:
        """绑定验证阶段依赖"""

        self.verify_config = verify_config
        self.build_config = build_config
        self.project_root = project_root
        self.semantic_precheck = semantic_precheck or SemanticPrecheck()
        self.semantic_guard = semantic_guard or SemanticGuard()
        self.load_tester = load_tester or LoadTester(build_config)
        self.smoke_tester = smoke_tester or SmokeTester(verify_config, project_root)
        self.regression_tester = regression_tester or RegressionTester()
        self.selftest_runner = selftest_runner or SelftestRunner()

    def empty_report(self) -> ValidationReport:
        """返回一份默认验证报告"""

        return ValidationReport(notes=["当前轮尚未执行验证。"])

    def run(
        self,
        *,
        task: TaskContext,
        attempt: AttemptRecord,
        attempt_dir: Path,
        rewritten_patch_path: Path,
        build_summary: BuildSummary | None = None,
        constraint_report: ConstraintReport | None = None,
        history_attempts: list[AttemptRecord] | None = None,
    ) -> tuple[ValidationReport, dict[str, Path]]:
        """执行第三期验证链，并返回报告及产物路径"""

        logs_dir = attempt_dir / "logs"
        artifacts_dir = attempt_dir / "artifacts"
        logs_dir.mkdir(parents=True, exist_ok=True)
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        risk_level = self._resolve_risk_level(constraint_report)
        validation_intensity = self._resolve_validation_intensity(risk_level)

        semantic_precheck_result = self.semantic_precheck.run(rewritten_patch_path=rewritten_patch_path)
        semantic_precheck_path = artifacts_dir / "semantic_precheck.json"
        semantic_precheck_path.write_text(semantic_precheck_result.model_dump_json(indent=2), encoding="utf-8")

        notes = [
            f"验证任务: {task.task_id}",
            f"构建状态: {attempt.status}",
            f"风险等级: {risk_level}",
            f"验证强度: {validation_intensity}",
        ]

        build_succeeded = attempt.status == "built"
        history_attempts = history_attempts or []

        load_result = self._pending_item("构建尚未产出可验证模块，暂不执行加载测试。")
        unload_result = self._pending_item("尚未执行加载测试，暂不执行卸载测试。")
        smoke_result = self._pending_item("尚未满足冒烟测试前置条件。")
        selftest_result = self._pending_item("当前轮尚未满足自检前置条件。")
        regression_result = self._pending_item("当前轮尚未生成回归基线。")

        if self.verify_config is None:
            notes.append("缺少 verify 配置，验证阶段仅保留结构化结果。")
        elif attempt.target_state == "target_already_patched":
            notes.append("本轮目标源码已包含修复，真实构建未执行，动态验证阶段不执行。")
            load_result = ValidationItem(status="skipped", ok=False, detail="目标源码已包含修复，真实构建未执行，未执行加载测试。")
            unload_result = ValidationItem(status="skipped", ok=False, detail="目标源码已包含修复，真实构建未执行，未执行卸载测试。")
            smoke_result = ValidationItem(status="skipped", ok=False, detail="目标源码已包含修复，真实构建未执行，未执行冒烟测试。")
            selftest_result = ValidationItem(status="skipped", ok=False, detail="目标源码已包含修复，真实构建未执行，未执行自检。")
            regression_result = ValidationItem(status="skipped", ok=False, detail="目标源码已包含修复，真实构建未执行，未执行回归验证。")
        elif not build_succeeded or attempt.module_path is None:
            notes.append("本轮未构建出模块产物，动态验证阶段维持待执行状态。")
        else:
            selftest_result, selftest_log = self.selftest_runner.run(
                build_succeeded=build_succeeded,
                module_path=attempt.module_path,
                risk_level=risk_level,
            )
            selftest_result = self._attach_log_path(selftest_result, logs_dir / "selftest.log")
            (logs_dir / "selftest.log").write_text(selftest_log, encoding="utf-8")

            if self.verify_config.enable_load_test:
                load_result, load_log = self.load_tester.load(
                    module_path=attempt.module_path,
                )
                load_result = self._attach_log_path(load_result, logs_dir / "load.log")
                (logs_dir / "load.log").write_text(load_log or f"{load_result.detail}\n", encoding="utf-8")
            else:
                load_result = ValidationItem(status="skipped", ok=False, detail="配置已关闭模块加载测试。")
                load_result = self._attach_log_path(load_result, logs_dir / "load.log")
                (logs_dir / "load.log").write_text(f"{load_result.detail}\n", encoding="utf-8")

            if self.verify_config.enable_unload_test and load_result.ok:
                unload_result, unload_log = self.load_tester.unload(
                    module_path=attempt.module_path,
                )
                unload_result = self._attach_log_path(unload_result, logs_dir / "unload.log")
                (logs_dir / "unload.log").write_text(unload_log or f"{unload_result.detail}\n", encoding="utf-8")
            elif self.verify_config.enable_unload_test:
                unload_result = self._pending_item("加载测试未通过，暂不执行卸载测试。")
                unload_result = self._attach_log_path(unload_result, logs_dir / "unload.log")
                (logs_dir / "unload.log").write_text(f"{unload_result.detail}\n", encoding="utf-8")
            else:
                unload_result = ValidationItem(status="skipped", ok=False, detail="配置已关闭模块卸载测试。")
                unload_result = self._attach_log_path(unload_result, logs_dir / "unload.log")
                (logs_dir / "unload.log").write_text(f"{unload_result.detail}\n", encoding="utf-8")

            should_run_smoke = self.verify_config.enable_smoke_test and load_result.ok
            if should_run_smoke:
                smoke_result, smoke_log = self.smoke_tester.run()
                smoke_result = self._attach_log_path(smoke_result, logs_dir / "smoke.log")
                (logs_dir / "smoke.log").write_text(smoke_log or f"{smoke_result.detail}\n", encoding="utf-8")
            elif self.verify_config.enable_smoke_test:
                smoke_result = self._pending_item("加载测试未通过或未执行，暂不执行冒烟测试。")
                smoke_result = self._attach_log_path(smoke_result, logs_dir / "smoke.log")
                (logs_dir / "smoke.log").write_text(f"{smoke_result.detail}\n", encoding="utf-8")
            else:
                smoke_result = ValidationItem(status="skipped", ok=False, detail="配置已关闭冒烟测试。")
                smoke_result = self._attach_log_path(smoke_result, logs_dir / "smoke.log")
                (logs_dir / "smoke.log").write_text(f"{smoke_result.detail}\n", encoding="utf-8")

        semantic_guard_enabled = self.verify_config is None or self.verify_config.enable_semantic_guard
        if semantic_guard_enabled:
            # 守卫放在动态验证结果之后执行，这样它可以区分模块问题和更像语义偏移的问题
            semantic_guard_result = self.semantic_guard.run(
                semantic_precheck=semantic_precheck_result,
                rewritten_patch_path=rewritten_patch_path,
                build_succeeded=build_succeeded,
                module_path=attempt.module_path,
                load_result=load_result,
                smoke_result=smoke_result,
                regression_result=regression_result,
            )
        else:
            semantic_guard_result = ValidationItem(status="skipped", ok=False, detail="配置已关闭语义守卫。")
        semantic_guard_path = artifacts_dir / "semantic_guard.json"
        semantic_guard_path.write_text(semantic_guard_result.model_dump_json(indent=2), encoding="utf-8")

        if self.verify_config is not None and self.verify_config.enable_regression:
            regression_result, regression_summary, regression_log = self.regression_tester.run(
                current_attempt=attempt,
                history_attempts=history_attempts,
                semantic_guard_passed=semantic_guard_result.ok,
            )
            regression_result = self._attach_log_path(regression_result, logs_dir / "regression.log")
            (logs_dir / "regression.log").write_text(regression_log or f"{regression_result.detail}\n", encoding="utf-8")
            regression_summary_path = artifacts_dir / "regression_summary.json"
            regression_summary_path.write_text(
                json.dumps(regression_summary, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            notes.append(f"回归测试结果: {regression_result.status}")
        else:
            regression_result = ValidationItem(status="skipped", ok=False, detail="配置已关闭回归验证。")
            regression_result = self._attach_log_path(regression_result, logs_dir / "regression.log")
            (logs_dir / "regression.log").write_text(f"{regression_result.detail}\n", encoding="utf-8")
            regression_summary_path = artifacts_dir / "regression_summary.json"
            regression_summary_path.write_text(
                json.dumps({"enabled": False, "detail": regression_result.detail}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        if semantic_guard_enabled:
            semantic_guard_result = self.semantic_guard.run(
                semantic_precheck=semantic_precheck_result,
                rewritten_patch_path=rewritten_patch_path,
                build_succeeded=build_succeeded,
                module_path=attempt.module_path,
                load_result=load_result,
                smoke_result=smoke_result,
                regression_result=regression_result,
            )
            semantic_guard_path.write_text(semantic_guard_result.model_dump_json(indent=2), encoding="utf-8")

        for item, path in [
            (selftest_result, logs_dir / "selftest.log"),
            (load_result, logs_dir / "load.log"),
            (unload_result, logs_dir / "unload.log"),
            (smoke_result, logs_dir / "smoke.log"),
            (regression_result, logs_dir / "regression.log"),
        ]:
            self._ensure_log_file(item=item, path=path)

        matrix = [
            self._matrix_entry(
                name="semantic_precheck",
                category="static",
                enabled=True,
                result=semantic_precheck_result,
                risk_level=risk_level,
            ),
            self._matrix_entry(
                name="selftest",
                category="dynamic",
                enabled=build_succeeded,
                result=selftest_result,
                risk_level=risk_level,
            ),
            self._matrix_entry(
                name="load_test",
                category="dynamic",
                enabled=self.verify_config.enable_load_test if self.verify_config is not None else False,
                result=load_result,
                risk_level=risk_level,
            ),
            self._matrix_entry(
                name="unload_test",
                category="dynamic",
                enabled=self.verify_config.enable_unload_test if self.verify_config is not None else False,
                result=unload_result,
                risk_level=risk_level,
            ),
            self._matrix_entry(
                name="smoke_test",
                category="dynamic",
                enabled=self.verify_config.enable_smoke_test if self.verify_config is not None else False,
                result=smoke_result,
                risk_level=risk_level,
            ),
            self._matrix_entry(
                name="semantic_guard",
                category="guard",
                enabled=semantic_guard_enabled,
                result=semantic_guard_result,
                risk_level=risk_level,
            ),
            self._matrix_entry(
                name="regression",
                category="regression",
                enabled=self.verify_config.enable_regression if self.verify_config is not None else False,
                result=regression_result,
                risk_level=risk_level,
            ),
        ]
        validation_matrix_path = artifacts_dir / "validation_matrix.json"
        validation_matrix_path.write_text(
            json.dumps([item.model_dump(mode="json") for item in matrix], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        overall_status = self._overall_status(
            load_result=load_result,
            unload_result=unload_result,
            smoke_result=smoke_result,
            selftest_result=selftest_result,
            regression_result=regression_result,
            semantic_guard_result=semantic_guard_result,
        )

        report = ValidationReport(
            semantic_precheck_result=semantic_precheck_result,
            load_result=load_result,
            unload_result=unload_result,
            smoke_result=smoke_result,
            selftest_result=selftest_result,
            regression_result=regression_result,
            semantic_guard_result=semantic_guard_result,
            validation_matrix=matrix,
            validation_intensity=validation_intensity,
            status=overall_status,
            notes=notes,
        )
        validation_report_path = artifacts_dir / "validation_report.json"
        validation_report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

        return report, {
            "semantic_precheck": semantic_precheck_path,
            "semantic_guard": semantic_guard_path,
            "validation_matrix": validation_matrix_path,
            "validation_report": validation_report_path,
            "selftest_log": logs_dir / "selftest.log",
            "load_log": logs_dir / "load.log",
            "unload_log": logs_dir / "unload.log",
            "smoke_log": logs_dir / "smoke.log",
            "regression_log": logs_dir / "regression.log",
            "regression_summary": regression_summary_path,
        }

    def _resolve_risk_level(self, constraint_report: ConstraintReport | None) -> str:
        """根据约束报告整理风险等级"""

        if constraint_report is None:
            return "low"
        if constraint_report.high_risk_count > 0 or constraint_report.requires_callback or constraint_report.requires_shadow_variable:
            return "high"
        if constraint_report.risk_items:
            return "medium"
        return "low"

    def _resolve_validation_intensity(self, risk_level: str) -> str:
        """按风险等级返回验证强度"""

        return {
            "low": "light",
            "medium": "standard",
            "high": "strict",
        }.get(risk_level, "light")

    def _overall_status(
        self,
        *,
        load_result: ValidationItem,
        unload_result: ValidationItem,
        smoke_result: ValidationItem,
        selftest_result: ValidationItem,
        regression_result: ValidationItem,
        semantic_guard_result: ValidationItem,
    ) -> str:
        """折叠整个验证阶段的总状态"""

        items = [load_result, unload_result, smoke_result, selftest_result, regression_result, semantic_guard_result]
        if any(item.status == "failed" for item in items):
            return "failed"
        if semantic_guard_result.ok and load_result.ok:
            return "passed"
        if any(item.status == "passed" for item in items):
            return "partial"
        return "pending"

    def _pending_item(self, detail: str) -> ValidationItem:
        """构造统一的待执行验证项"""

        return ValidationItem(status="pending", ok=False, detail=detail)

    def _attach_log_path(self, item: ValidationItem, path: Path) -> ValidationItem:
        """把日志路径补回验证项"""

        return item.model_copy(update={"log_path": str(path)})

    def _matrix_entry(
        self,
        *,
        name: str,
        category: str,
        enabled: bool,
        result: ValidationItem,
        risk_level: str,
    ) -> ValidationMatrixEntry:
        """把单项验证结果折叠成矩阵条目"""

        return ValidationMatrixEntry(
            name=name,
            category=category,
            enabled=enabled,
            status=result.status,
            risk_level=risk_level,
            detail=result.detail,
            log_path=result.log_path,
        )

    def _ensure_log_file(self, *, item: ValidationItem, path: Path) -> None:
        """在验证项未真正执行时，也保留一份占位日志"""

        if path.exists():
            return
        path.write_text(f"{item.detail}\n", encoding="utf-8")
