from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from patchweaver.models.attempt import AttemptRecord, BuildSummary
from patchweaver.models.constraint import ConstraintReport, RiskItem
from patchweaver.models.task import TaskContext
from patchweaver.models.validation import ValidationItem
from patchweaver.validator.validator import Validator


def _case_dir(case_name: str) -> Path:
    base_dir = Path("E:/Desk/patchweaver_pytest_cases")
    base_dir.mkdir(parents=True, exist_ok=True)
    root = base_dir / f"{case_name}-{uuid4().hex[:8]}"
    root.mkdir(parents=True, exist_ok=True)
    return root


class _LoadTesterStub:
    def load(self, *, module_path: Path | None):
        return ValidationItem(status="passed", ok=True, detail="模块加载测试通过。"), "load ok\n"

    def unload(self, *, module_path: Path | None):
        return ValidationItem(status="passed", ok=True, detail="模块卸载测试通过。"), "unload ok\n"


class _SmokeTesterStub:
    def run(self):
        return ValidationItem(status="passed", ok=True, detail="冒烟测试通过。"), "smoke ok\n"


class _RegressionTesterStub:
    def run(self, *, current_attempt, history_attempts, semantic_guard_passed):
        return (
            ValidationItem(status="passed", ok=True, detail="回归检查通过。"),
            {"history_attempts": len(history_attempts), "improved": True},
            "regression ok\n",
        )


class _SelftestRunnerStub:
    def run(self, *, build_succeeded: bool, module_path: Path | None, risk_level: str):
        return ValidationItem(status="passed", ok=True, detail=f"自检通过，风险等级 {risk_level}。"), "selftest ok\n"


def test_validator_generates_phase3_validation_artifacts() -> None:
    tmp_path = _case_dir("validator-phase3")
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    attempt_dir = tmp_path / "attempt"
    rewritten_patch = attempt_dir / "rewrite" / "rewritten.patch"
    rewritten_patch.parent.mkdir(parents=True, exist_ok=True)
    rewritten_patch.write_text(
        "\n".join(
            [
                "diff --git a/kernel/demo.c b/kernel/demo.c",
                "--- a/kernel/demo.c",
                "+++ b/kernel/demo.c",
                "@@ -1 +1 @@",
                "-old_value();",
                "+new_value();",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    module_path = attempt_dir / "artifacts" / "demo_patch.ko"
    module_path.parent.mkdir(parents=True, exist_ok=True)
    module_path.write_text("fake ko\n", encoding="utf-8")

    verify_config = SimpleNamespace(
        enable_semantic_guard=True,
        enable_load_test=True,
        enable_unload_test=True,
        enable_smoke_test=True,
        enable_regression=True,
        smoke_test_script="scripts/validate_smoke.sh",
    )
    build_config = SimpleNamespace(build_backend="local")
    task = TaskContext(
        task_id="TASK-VAL-001",
        cve_id="CVE-2099-0999",
        target_kernel="6.6.102-5.2.an23.x86_64",
        workspace_dir=tmp_path / "workspace",
    )
    attempt = AttemptRecord(
        task_id=task.task_id,
        attempt_no=2,
        attempt_id=f"{task.task_id}-A002",
        status="built",
        module_path=module_path,
        rewritten_patch_path=rewritten_patch,
    )
    build_summary = BuildSummary(
        task_id=task.task_id,
        attempt_id=attempt.attempt_id,
        backend="local",
        builder_cmd="kpatch-build",
        status="built",
        summary="unit test build summary",
        rewritten_patch_path=rewritten_patch,
        module_path=module_path,
    )
    constraint_report = ConstraintReport(
        task_id=task.task_id,
        risk_items=[
            RiskItem(
                risk_type="missing_fentry",
                severity="high",
                required_primitives=["wrapper"],
            )
        ],
        high_risk_count=1,
    )

    validator = Validator(
        verify_config=verify_config,
        build_config=build_config,
        project_root=project_root,
        load_tester=_LoadTesterStub(),
        smoke_tester=_SmokeTesterStub(),
        regression_tester=_RegressionTesterStub(),
        selftest_runner=_SelftestRunnerStub(),
    )

    report, artifacts = validator.run(
        task=task,
        attempt=attempt,
        attempt_dir=attempt_dir,
        rewritten_patch_path=rewritten_patch,
        build_summary=build_summary,
        constraint_report=constraint_report,
        history_attempts=[
            AttemptRecord(
                task_id=task.task_id,
                attempt_no=1,
                attempt_id=f"{task.task_id}-A001",
                status="failed",
                failure_type="missing_fentry",
            )
        ],
    )

    assert report.status == "passed"
    assert report.validation_intensity == "strict"
    assert len(report.validation_matrix) == 7
    assert artifacts["validation_matrix"].exists()
    assert artifacts["semantic_guard"].exists()
    assert artifacts["regression_summary"].exists()
