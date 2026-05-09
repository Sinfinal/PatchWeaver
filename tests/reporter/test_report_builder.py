from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from patchweaver.models.attempt import AttemptRecord
from patchweaver.models.harness import ArtifactRef
from patchweaver.models.task import TaskContext
from patchweaver.models.validation import ValidationItem, ValidationMatrixEntry, ValidationReport
from patchweaver.reporter.md_writer import MdWriter
from patchweaver.reporter.report_builder import ReportBuilder


def _project_root() -> Path:
    current = Path(__file__).resolve().parent
    for candidate in (current, *current.parents):
        if (candidate / "pyproject.toml").exists():
            return candidate
    raise RuntimeError(f"Unable to locate project root from {__file__}")


def _case_dir(case_name: str) -> Path:
    base_dir = _project_root() / "data" / "cache" / "pytest-tmp"
    base_dir.mkdir(parents=True, exist_ok=True)
    root = base_dir / f"{case_name}-{uuid4().hex[:8]}"
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_report_builder_marks_failure_closure_ready() -> None:
    tmp_path = _case_dir("report-builder-failure")
    task = TaskContext(
        task_id="TASK-RPT-001",
        cve_id="CVE-2099-1001",
        target_kernel="6.6.102-5.2.an23.x86_64",
        workspace_dir=tmp_path / "workspace",
    )
    attempts = [
        AttemptRecord(
            task_id=task.task_id,
            attempt_no=1,
            attempt_id=f"{task.task_id}-A001",
            status="failed",
            failure_type="compile_failed",
        )
    ]
    harness_trace = tmp_path / "attempts" / "001" / "trace" / "harness_trace.json"
    failure_record = tmp_path / "attempts" / "001" / "logs" / "failure_record.json"
    harness_trace.parent.mkdir(parents=True, exist_ok=True)
    failure_record.parent.mkdir(parents=True, exist_ok=True)
    harness_trace.write_text("{}\n", encoding="utf-8")
    failure_record.write_text("{}\n", encoding="utf-8")

    report = ReportBuilder(tmp_path).build_report(
        task=task,
        attempts=attempts,
        artifacts=[
            ArtifactRef(artifact_type="harness_trace", artifact_path=harness_trace),
            ArtifactRef(artifact_type="failure_record", artifact_path=failure_record),
        ],
    )

    assert report.closure_summary["closure_type"] == "failure"
    assert report.closure_summary["closure_status"] == "ready"
    assert report.closure_summary["success_replay_ready"] is False
    assert report.closure_summary["missing_success_evidence"] == []
    assert any("compile_failed" in item for item in report.known_limits)


def test_report_builder_marks_success_replay_ready_when_validation_passed() -> None:
    tmp_path = _case_dir("report-builder-success")
    task = TaskContext(
        task_id="TASK-RPT-002",
        cve_id="CVE-2099-1002",
        target_kernel="6.6.102-5.2.an23.x86_64",
        workspace_dir=tmp_path / "workspace",
    )
    attempt_dir = tmp_path / "attempts" / "001"
    artifacts_dir = attempt_dir / "artifacts"
    logs_dir = attempt_dir / "logs"
    rewrite_dir = attempt_dir / "rewrite"
    trace_dir = attempt_dir / "trace"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    rewrite_dir.mkdir(parents=True, exist_ok=True)
    trace_dir.mkdir(parents=True, exist_ok=True)

    module_path = artifacts_dir / "demo_patch.ko"
    build_log = logs_dir / "build.log"
    rewritten_patch = rewrite_dir / "rewritten.patch"
    validation_report_path = artifacts_dir / "validation_report.json"
    validation_matrix_path = artifacts_dir / "validation_matrix.json"
    selftest_log = logs_dir / "selftest.log"
    load_log = logs_dir / "load.log"
    unload_log = logs_dir / "unload.log"
    smoke_log = logs_dir / "smoke.log"
    harness_trace = trace_dir / "harness_trace.json"

    for path, content in [
        (module_path, "fake ko\n"),
        (build_log, "build ok\n"),
        (rewritten_patch, "diff --git a/demo b/demo\n"),
        (selftest_log, "selftest ok\n"),
        (load_log, "load ok\n"),
        (unload_log, "unload ok\n"),
        (smoke_log, "smoke ok\n"),
        (harness_trace, "{}\n"),
    ]:
        path.write_text(content, encoding="utf-8")

    validation_report = ValidationReport(
        semantic_precheck_result=ValidationItem(status="passed", ok=True, detail="ok"),
        load_result=ValidationItem(status="passed", ok=True, detail="ok"),
        unload_result=ValidationItem(status="passed", ok=True, detail="ok"),
        smoke_result=ValidationItem(status="passed", ok=True, detail="ok"),
        selftest_result=ValidationItem(status="passed", ok=True, detail="ok"),
        regression_result=ValidationItem(status="skipped", ok=False, detail="disabled"),
        semantic_guard_result=ValidationItem(status="passed", ok=True, detail="ok"),
        validation_matrix=[
            ValidationMatrixEntry(name="load_test", category="dynamic", status="passed", risk_level="low", detail="ok")
        ],
        validation_intensity="standard",
        status="passed",
        notes=["验证档位: standard"],
    )
    validation_report_path.write_text(validation_report.model_dump_json(indent=2), encoding="utf-8")
    validation_matrix_path.write_text("[]\n", encoding="utf-8")

    attempts = [
        AttemptRecord(
            task_id=task.task_id,
            attempt_no=1,
            attempt_id=f"{task.task_id}-A001",
            status="built",
            build_exec_status="executed",
            module_path=module_path,
            rewritten_patch_path=rewritten_patch,
            build_log_path=build_log,
        )
    ]

    report = ReportBuilder(tmp_path).build_report(
        task=task,
        attempts=attempts,
        artifacts=[
            ArtifactRef(artifact_type="harness_trace", artifact_path=harness_trace),
            ArtifactRef(artifact_type="rewritten_patch", artifact_path=rewritten_patch),
            ArtifactRef(artifact_type="build_log", artifact_path=build_log),
            ArtifactRef(artifact_type="validation_report", artifact_path=validation_report_path),
            ArtifactRef(artifact_type="validation_matrix", artifact_path=validation_matrix_path),
            ArtifactRef(artifact_type="selftest_log", artifact_path=selftest_log),
            ArtifactRef(artifact_type="load_log", artifact_path=load_log),
            ArtifactRef(artifact_type="unload_log", artifact_path=unload_log),
            ArtifactRef(artifact_type="smoke_log", artifact_path=smoke_log),
        ],
    )

    assert report.closure_summary["closure_type"] == "success"
    assert report.closure_summary["success_replay_ready"] is True
    assert report.validation_summary["validation_status"] == "passed"
    assert report.closure_summary["missing_success_evidence"] == []
    assert any(item.endswith("validation_report.json") for item in report.replay_summary["recommended_replay_files"])


def test_report_builder_surfaces_agent_decision_summary_in_report_and_markdown() -> None:
    tmp_path = _case_dir("report-builder-agent-decision")
    task = TaskContext(
        task_id="TASK-RPT-003",
        cve_id="CVE-2099-1003",
        target_kernel="6.6.102-5.2.an23.x86_64",
        workspace_dir=tmp_path / "workspace",
        status="failed",
    )
    attempt_dir = task.workspace_dir / "attempts" / "001"
    repair_intent_path = task.workspace_dir / "analysis" / "repair_intent.json"
    rewrite_plan_path = attempt_dir / "rewrite" / "rewrite_plan.json"
    failure_record_path = attempt_dir / "logs" / "failure_record.json"
    build_summary_path = attempt_dir / "artifacts" / "build_summary.json"
    for path in [repair_intent_path, rewrite_plan_path, failure_record_path, build_summary_path]:
        path.parent.mkdir(parents=True, exist_ok=True)

    repair_intent_path.write_text(
        json.dumps(
            {
                "cve_id": task.cve_id,
                "bug_class": "bounds_check",
                "root_cause": "missing length guard",
                "guard_conditions": ["if (len > max) return -EINVAL;"],
                "recommended_strategy": "semantic_guard",
                "confidence": 0.84,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    rewrite_plan_path.write_text(
        json.dumps(
            {
                "selected_recipe": "smpl_primary_rewrite",
                "selected_strategy": "smpl_template",
                "selection_reason": "fallback to template rewrite",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    failure_record_path.write_text(
        json.dumps(
            {
                "stage_name": "build",
                "failure_type": "compile_failed",
                "summary": "struct field mismatch",
                "agent_next_action": "adapt field access before retry",
                "diagnostic_details": {"compiler_error": "no member named max"},
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    build_summary_path.write_text(
        json.dumps({"failure_type": "compile_failed", "build_exec_status": "executed"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    attempts = [
        AttemptRecord(
            task_id=task.task_id,
            attempt_no=1,
            attempt_id=f"{task.task_id}-A001",
            status="failed",
            failure_type="compile_failed",
            build_exec_status="executed",
        )
    ]
    report = ReportBuilder(tmp_path).build_report(
        task=task,
        attempts=attempts,
        artifacts=[
            ArtifactRef(artifact_type="repair_intent", artifact_path=repair_intent_path),
            ArtifactRef(artifact_type="rewrite_plan", artifact_path=rewrite_plan_path),
            ArtifactRef(artifact_type="failure_record", artifact_path=failure_record_path),
            ArtifactRef(artifact_type="build_summary", artifact_path=build_summary_path),
        ],
    )

    summary = report.agent_decision_summary
    assert summary["repair_intent"]["recommended_strategy"] == "semantic_guard"
    assert summary["selected_recipe"] == "smpl_primary_rewrite"
    assert summary["selected_strategy"] == "smpl_template"
    assert summary["strategy_switch"]["switched"] is True
    assert summary["failure_attribution"]["failure_type"] == "compile_failed"
    assert summary["failure_attribution"]["agent_next_action"] == "adapt field access before retry"
    assert summary["source_exists"]["repair_intent"] is True

    md_path = tmp_path / "report.md"
    MdWriter().write_report(report, md_path)
    markdown = md_path.read_text(encoding="utf-8")
    assert "Agent Decision Summary" in markdown
    assert "semantic_guard" in markdown
    assert "compile_failed" in markdown
