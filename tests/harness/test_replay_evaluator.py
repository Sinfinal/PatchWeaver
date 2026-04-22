from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from patchweaver.harness.evaluator import Evaluator
from patchweaver.harness.replay import ReplayHarness
from patchweaver.models.attempt import AttemptRecord
from patchweaver.models.harness import ArtifactRef
from patchweaver.models.task import TaskContext
from patchweaver.models.validation import ValidationItem, ValidationMatrixEntry, ValidationReport


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


def test_evaluator_summarizes_attempts_and_artifacts() -> None:
    tmp_path = _case_dir("replay-evaluator")
    attempts = [
        AttemptRecord(task_id="TASK-EVAL-001", attempt_no=1, attempt_id="TASK-EVAL-001-A001", status="failed", failure_type="patch_apply_failed"),
        AttemptRecord(task_id="TASK-EVAL-001", attempt_no=2, attempt_id="TASK-EVAL-001-A002", status="built"),
    ]
    artifacts = [
        ArtifactRef(artifact_type="rewrite_plan", artifact_path=tmp_path / "rewrite_plan.json"),
        ArtifactRef(artifact_type="rewrite_plan", artifact_path=tmp_path / "rewrite_plan_2.json"),
        ArtifactRef(artifact_type="validation_report", artifact_path=tmp_path / "validation_report.json"),
    ]

    summary = Evaluator().summarize(attempts=attempts, artifacts=artifacts)

    assert summary["total_attempts"] == 2
    assert summary["built_attempts"] == 1
    assert summary["failed_attempts"] == 1
    assert summary["failure_breakdown"]["patch_apply_failed"] == 1
    assert summary["artifact_type_counts"]["rewrite_plan"] == 2
    assert summary["latest_status"] == "built"


def test_replay_harness_collects_stage_routes_dispatch_modes_and_files() -> None:
    tmp_path = _case_dir("replay-summary")
    task = TaskContext(
        task_id="TASK-REPLAY-001",
        cve_id="CVE-2099-0011",
        target_kernel="6.6.102-5.2.an23.x86_64",
        workspace_dir=tmp_path / "workspace",
    )
    task_dir = tmp_path / task.task_id
    attempt_dir = task_dir / "attempts" / "001"
    (task_dir / "reports").mkdir(parents=True, exist_ok=True)
    (task_dir / "reports" / "report.json").write_text("{\"status\": \"ok\"}\n", encoding="utf-8")
    (attempt_dir / "prompt").mkdir(parents=True, exist_ok=True)
    (attempt_dir / "logs").mkdir(parents=True, exist_ok=True)
    (attempt_dir / "trace").mkdir(parents=True, exist_ok=True)
    (attempt_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    (attempt_dir / "prompt" / "rewrite_recipe_prompt_packet.json").write_text("{}\n", encoding="utf-8")
    (attempt_dir / "logs" / "failure_record.json").write_text("{}\n", encoding="utf-8")
    (attempt_dir / "trace" / "harness_trace.json").write_text("{}\n", encoding="utf-8")
    (attempt_dir / "attempt_state.json").write_text("{}\n", encoding="utf-8")
    (attempt_dir / "artifacts" / "validation_report.json").write_text("{}\n", encoding="utf-8")

    attempts = [
        AttemptRecord(
            task_id=task.task_id,
            attempt_no=1,
            attempt_id=f"{task.task_id}-A001",
            status="failed",
            failure_type="compile_failed",
        )
    ]
    latest_trace = {
        "trace_path": str(attempt_dir / "trace" / "harness_trace.json"),
        "summary": {
            "extras": {
                "stage_routes": {
                    "rewrite_recipe": {
                        "selected_skill": "rewrite_recipe",
                        "candidate_skills": ["rewrite_recipe"],
                        "selection_reason": "unit test route",
                    }
                },
                "dispatch_modes": {
                    "rewrite_recipe": "write-exclusive",
                    "failure_analysis": "read-parallel",
                },
            }
        },
    }

    summary = ReplayHarness(tmp_path).build_summary(
        task=task,
        task_dir=task_dir,
        attempts=attempts,
        latest_trace=latest_trace,
        replay_comparison={"attempt_count": 1, "items": [{"attempt_no": 1}]},
    )

    assert summary["latest_attempt_id"] == f"{task.task_id}-A001"
    assert summary["stage_routes"]["rewrite_recipe"]["selected_skill"] == "rewrite_recipe"
    assert summary["dispatch_modes"]["failure_analysis"] == "read-parallel"
    assert len(summary["replay_files"]) == 5
    assert summary["report_path"] == f"{task.task_id}/reports/report.json"
    assert summary["closure_paths"]["task_dir"] == task.task_id
    assert summary["comparison"]["attempt_count"] == 1
    assert summary["closure_type"] == "failure"
    assert summary["closure_status"] == "ready"
    assert summary["success_replay_ready"] is False
    assert summary["missing_success_evidence"] == []


def test_replay_harness_marks_success_replay_ready() -> None:
    tmp_path = _case_dir("replay-success")
    task = TaskContext(
        task_id="TASK-REPLAY-002",
        cve_id="CVE-2099-0012",
        target_kernel="6.6.102-5.2.an23.x86_64",
        workspace_dir=tmp_path / "workspace",
    )
    task_dir = tmp_path / task.task_id
    attempt_dir = task_dir / "attempts" / "001"
    (task_dir / "reports").mkdir(parents=True, exist_ok=True)
    (task_dir / "reports" / "report.json").write_text("{\"status\": \"ok\"}\n", encoding="utf-8")
    (task_dir / "reports" / "evaluation_summary.json").write_text("{\"success_rate\": 1.0}\n", encoding="utf-8")
    (attempt_dir / "rewrite").mkdir(parents=True, exist_ok=True)
    (attempt_dir / "logs").mkdir(parents=True, exist_ok=True)
    (attempt_dir / "trace").mkdir(parents=True, exist_ok=True)
    (attempt_dir / "artifacts").mkdir(parents=True, exist_ok=True)

    rewritten_patch = attempt_dir / "rewrite" / "rewritten.patch"
    build_log = attempt_dir / "logs" / "build.log"
    selftest_log = attempt_dir / "logs" / "selftest.log"
    load_log = attempt_dir / "logs" / "load.log"
    unload_log = attempt_dir / "logs" / "unload.log"
    smoke_log = attempt_dir / "logs" / "smoke.log"
    regression_log = attempt_dir / "logs" / "regression.log"
    harness_trace = attempt_dir / "trace" / "harness_trace.json"
    validation_report_path = attempt_dir / "artifacts" / "validation_report.json"
    validation_matrix_path = attempt_dir / "artifacts" / "validation_matrix.json"
    module_path = attempt_dir / "artifacts" / "livepatch_demo.ko"

    for path, content in [
        (rewritten_patch, "diff --git a/demo b/demo\n"),
        (build_log, "build ok\n"),
        (selftest_log, "selftest ok\n"),
        (load_log, "load ok\n"),
        (unload_log, "unload ok\n"),
        (smoke_log, "smoke ok\n"),
        (regression_log, "regression skipped\n"),
        (harness_trace, "{}\n"),
        (module_path, "fake ko\n"),
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
        notes=["验证通过"],
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
            build_log_path=build_log,
            rewritten_patch_path=rewritten_patch,
        )
    ]
    latest_trace = {
        "trace_path": str(harness_trace),
        "summary": {
            "extras": {
                "stage_routes": {
                    "validation": {
                        "selected_skill": "validation",
                        "candidate_skills": ["validation"],
                        "selection_reason": "unit test route",
                    }
                },
                "dispatch_modes": {
                    "validation": "read-parallel",
                },
            }
        },
    }

    summary = ReplayHarness(tmp_path).build_summary(
        task=task,
        task_dir=task_dir,
        attempts=attempts,
        latest_trace=latest_trace,
        replay_comparison={"attempt_count": 1, "items": [{"attempt_no": 1}]},
    )

    assert summary["closure_type"] == "success"
    assert summary["closure_status"] == "ready"
    assert summary["success_replay_ready"] is True
    assert summary["missing_success_evidence"] == []
    assert any(item.endswith("validation_report.json") for item in summary["replay_files"])
    assert any(item.endswith("rewritten.patch") for item in summary["success_replay_files"])


def test_evaluator_summarizes_fixture_set() -> None:
    summary = Evaluator().summarize_fixture_set(
        fixture_name="contest_samples",
        fixtures=[
            {"fixture_id": "fixture-1"},
            {"fixture_id": "fixture-2"},
        ],
        results=[
            {
                "fixture_id": "fixture-1",
                "fixture_group": "challenge",
                "final_status": "built",
                "attempts": 2,
                "latest_failure_type": None,
            },
            {
                "fixture_id": "fixture-2",
                "fixture_group": "holdout",
                "final_status": "failed",
                "attempts": 3,
                "latest_failure_type": "compile_failed",
            },
        ],
    )

    assert summary["fixture_name"] == "contest_samples"
    assert summary["matched_fixtures"] == 2
    assert summary["success_count"] == 1
    assert summary["failed_count"] == 1
    assert summary["success_rate"] == 0.5
    assert summary["status_distribution"]["built"] == 1
    assert summary["failure_distribution"]["compile_failed"] == 1
    assert summary["group_distribution"]["challenge"] == 1


def test_evaluator_skips_missing_fixture_from_summary() -> None:
    summary = Evaluator().summarize_fixture_set(
        fixture_name="contest_samples",
        fixtures=[
            {"fixture_id": "fixture-1"},
            {"fixture_id": "fixture-2"},
        ],
        results=[
            {
                "fixture_id": "fixture-1",
                "matched": True,
                "fixture_group": "holdout",
                "final_status": "failed",
                "attempts": 1,
                "latest_failure_type": "patch_apply_failed",
            },
            {
                "fixture_id": "fixture-2",
                "matched": False,
                "final_status": "missing",
                "attempts": 0,
                "latest_failure_type": None,
            },
        ],
    )

    assert summary["matched_fixtures"] == 1
    assert summary["missing_fixtures"] == 1
    assert summary["average_attempts"] == 1.0
    assert summary["failure_distribution"]["patch_apply_failed"] == 1
    assert summary["group_distribution"]["holdout"] == 1
