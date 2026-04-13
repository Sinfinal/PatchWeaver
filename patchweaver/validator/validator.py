"""验证编排器。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from patchweaver.models.attempt import AttemptRecord, BuildSummary
from patchweaver.models.task import TaskContext
from patchweaver.models.validation import ValidationItem, ValidationReport
from patchweaver.validator.load_tester import LoadTester
from patchweaver.validator.regression_tester import RegressionTester
from patchweaver.validator.semantic_guard import SemanticGuard
from patchweaver.validator.semantic_precheck import SemanticPrecheck
from patchweaver.validator.smoke_tester import SmokeTester


class Validator:
    """负责组织加载、卸载、冒烟和最小语义守卫。"""

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
    ) -> None:
        """绑定验证阶段依赖。"""

        self.verify_config = verify_config
        self.build_config = build_config
        self.project_root = project_root
        self.semantic_precheck = semantic_precheck or SemanticPrecheck()
        self.semantic_guard = semantic_guard or SemanticGuard()
        self.load_tester = load_tester or LoadTester(build_config)
        self.smoke_tester = smoke_tester or SmokeTester(verify_config, project_root)
        self.regression_tester = regression_tester or RegressionTester()

    def empty_report(self) -> ValidationReport:
        """返回一份默认验证报告。"""

        return ValidationReport(notes=["当前轮尚未执行验证。"])

    def run(
        self,
        *,
        task: TaskContext,
        attempt: AttemptRecord,
        attempt_dir: Path,
        rewritten_patch_path: Path,
        build_summary: BuildSummary | None = None,
    ) -> tuple[ValidationReport, dict[str, Path]]:
        """执行最小真实验证链，并返回报告及产物路径。"""

        logs_dir = attempt_dir / "logs"
        artifacts_dir = attempt_dir / "artifacts"
        logs_dir.mkdir(parents=True, exist_ok=True)
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        precheck_result = self.semantic_precheck.run(rewritten_patch_path=rewritten_patch_path)
        semantic_precheck_path = artifacts_dir / "semantic_precheck.json"
        semantic_precheck_path.write_text(precheck_result.model_dump_json(indent=2), encoding="utf-8")

        notes = [f"验证任务: {task.task_id}", f"构建状态: {attempt.status}"]
        load_result = self._pending_item("构建尚未产出可验证模块，暂不执行加载测试。")
        unload_result = self._pending_item("尚未执行加载测试，暂不执行卸载测试。")
        smoke_result = self._pending_item("尚未满足冒烟测试前置条件。")

        remote_module_path = build_summary.remote_module_path if build_summary is not None else None
        build_succeeded = attempt.status == "built"

        if self.verify_config is None:
            notes.append("缺少 verify 配置，验证阶段仅保留结构化占位结果。")
        elif not build_succeeded or attempt.module_path is None:
            notes.append("本轮未构建出模块产物，验证阶段输出待执行说明。")
        else:
            if self.verify_config.enable_load_test:
                load_result, load_log = self.load_tester.load(module_path=attempt.module_path, remote_module_path=remote_module_path)
                load_result = self._attach_log_path(load_result, logs_dir / "load.log")
                (logs_dir / "load.log").write_text(load_log or f"{load_result.detail}\n", encoding="utf-8")
            else:
                load_result = ValidationItem(status="skipped", ok=False, detail="配置已关闭模块加载测试。")
                (logs_dir / "load.log").write_text(f"{load_result.detail}\n", encoding="utf-8")

            if self.verify_config.enable_unload_test and load_result.ok:
                unload_result, unload_log = self.load_tester.unload(module_path=attempt.module_path, remote_module_path=remote_module_path)
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

            if self.verify_config.enable_smoke_test and load_result.ok:
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

        if not (logs_dir / "load.log").exists():
            load_result = self._attach_log_path(load_result, logs_dir / "load.log")
            (logs_dir / "load.log").write_text(f"{load_result.detail}\n", encoding="utf-8")
        if not (logs_dir / "unload.log").exists():
            unload_result = self._attach_log_path(unload_result, logs_dir / "unload.log")
            (logs_dir / "unload.log").write_text(f"{unload_result.detail}\n", encoding="utf-8")
        if not (logs_dir / "smoke.log").exists():
            smoke_result = self._attach_log_path(smoke_result, logs_dir / "smoke.log")
            (logs_dir / "smoke.log").write_text(f"{smoke_result.detail}\n", encoding="utf-8")

        if self.verify_config is not None and self.verify_config.enable_regression:
            regression_result, regression_log = self.regression_tester.run()
            notes.append(f"回归测试结果: {regression_result.status}")
            (logs_dir / "regression.log").write_text(regression_log or f"{regression_result.detail}\n", encoding="utf-8")

        semantic_guard_result = self.semantic_guard.run(
            semantic_precheck=precheck_result,
            rewritten_patch_path=rewritten_patch_path,
            build_succeeded=build_succeeded,
            module_path=attempt.module_path,
        )

        report = ValidationReport(
            load_result=load_result,
            unload_result=unload_result,
            smoke_result=smoke_result,
            semantic_guard_result=semantic_guard_result,
            notes=notes,
        )
        validation_report_path = artifacts_dir / "validation_report.json"
        validation_report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

        return report, {
            "semantic_precheck": semantic_precheck_path,
            "validation_report": validation_report_path,
            "load_log": logs_dir / "load.log",
            "unload_log": logs_dir / "unload.log",
            "smoke_log": logs_dir / "smoke.log",
        }

    def _pending_item(self, detail: str) -> ValidationItem:
        """构造统一的待执行验证项。"""

        return ValidationItem(status="pending", ok=False, detail=detail)

    def _attach_log_path(self, item: ValidationItem, path: Path) -> ValidationItem:
        """把日志路径补回验证项。"""

        return item.model_copy(update={"log_path": str(path)})
