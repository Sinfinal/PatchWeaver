from __future__ import annotations

from pathlib import Path
import tempfile
from types import SimpleNamespace
from uuid import uuid4

from patchweaver.models.attempt import AttemptRecord, BuildSummary
from patchweaver.models.constraint import ConstraintReport, RiskItem
from patchweaver.models.task import TaskContext
from patchweaver.models.validation import ValidationItem
from patchweaver.validator.validator import Validator


def _project_root() -> Path:
    current = Path(__file__).resolve().parent
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").exists():
            return candidate
    raise RuntimeError(f"Unable to locate project root from {__file__}")


def _case_dir(case_name: str) -> Path:
    base_dir = Path(tempfile.gettempdir()) / "patchweaver-pytest"
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
        verification_profile="strict",
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
        target_files=["kernel/demo.c"],
        target_functions=["demo_fentry_target"],
        risk_items=[
            RiskItem(
                risk_type="no_fentry_target",
                severity="high",
                required_primitives=["wrapper", "callback"],
            )
        ],
        dominant_risk_types=["no_fentry_target"],
        suggested_primitives=["wrapper", "callback"],
        high_risk_count=1,
        requires_callback=True,
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


def test_validator_strict_profile_forces_guard_and_regression(tmp_path: Path) -> None:
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
        verification_profile="strict",
        enable_semantic_guard=False,
        enable_load_test=True,
        enable_unload_test=True,
        enable_smoke_test=True,
        enable_regression=False,
        smoke_test_script="scripts/validate_smoke.sh",
    )
    task = TaskContext(
        task_id="TASK-VAL-002",
        cve_id="CVE-2099-0998",
        target_kernel="6.6.102-5.2.an23.x86_64",
        workspace_dir=tmp_path / "workspace",
    )
    attempt = AttemptRecord(
        task_id=task.task_id,
        attempt_no=1,
        attempt_id=f"{task.task_id}-A001",
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

    validator = Validator(
        verify_config=verify_config,
        build_config=SimpleNamespace(build_backend="local"),
        project_root=tmp_path / "project",
        load_tester=_LoadTesterStub(),
        smoke_tester=_SmokeTesterStub(),
        regression_tester=_RegressionTesterStub(),
        selftest_runner=_SelftestRunnerStub(),
    )

    report, _ = validator.run(
        task=task,
        attempt=attempt,
        attempt_dir=attempt_dir,
        rewritten_patch_path=rewritten_patch,
        build_summary=build_summary,
        constraint_report=ConstraintReport(
            task_id=task.task_id,
            high_risk_count=1,
        ),
        history_attempts=[
            AttemptRecord(
                task_id=task.task_id,
                attempt_no=0,
                attempt_id=f"{task.task_id}-A000",
                status="failed",
                failure_type="compile_failed",
            )
        ],
    )

    assert any("验证档位: strict" == note for note in report.notes)
    assert report.semantic_guard_result.status == "passed"
    assert report.regression_result.status == "passed"


def test_validator_dev_profile_passes_when_enabled_dynamic_checks_pass(tmp_path: Path) -> None:
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

    task = TaskContext(
        task_id="TASK-VAL-DEV",
        cve_id="CVE-2099-0997",
        target_kernel="6.6.102-5.2.an23.x86_64",
        workspace_dir=tmp_path / "workspace",
    )
    attempt = AttemptRecord(
        task_id=task.task_id,
        attempt_no=1,
        attempt_id=f"{task.task_id}-A001",
        status="built",
        module_path=module_path,
        rewritten_patch_path=rewritten_patch,
    )

    validator = Validator(
        verify_config=SimpleNamespace(
            verification_profile="dev",
            enable_semantic_guard=False,
            enable_load_test=True,
            enable_unload_test=True,
            enable_smoke_test=True,
            enable_regression=False,
            smoke_test_script="scripts/validate_smoke.sh",
        ),
        build_config=SimpleNamespace(build_backend="local"),
        project_root=tmp_path / "project",
        load_tester=_LoadTesterStub(),
        smoke_tester=_SmokeTesterStub(),
        regression_tester=_RegressionTesterStub(),
        selftest_runner=_SelftestRunnerStub(),
    )

    report, _ = validator.run(
        task=task,
        attempt=attempt,
        attempt_dir=attempt_dir,
        rewritten_patch_path=rewritten_patch,
        build_summary=BuildSummary(
            task_id=task.task_id,
            attempt_id=attempt.attempt_id,
            backend="local",
            builder_cmd="kpatch-build",
            status="built",
            summary="unit test build summary",
            rewritten_patch_path=rewritten_patch,
            module_path=module_path,
        ),
        constraint_report=ConstraintReport(task_id=task.task_id),
        history_attempts=[],
    )

    assert report.status == "passed"
    assert report.semantic_guard_result.status == "skipped"
    assert report.regression_result.status == "skipped"
