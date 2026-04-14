from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from patchweaver.harness.evaluator import Evaluator
from patchweaver.harness.replay import ReplayHarness
from patchweaver.models.attempt import AttemptRecord
from patchweaver.models.harness import ArtifactRef
from patchweaver.models.task import TaskContext


def _case_dir(case_name: str) -> Path:
    base_dir = Path("E:/Desk/patchweaver_pytest_cases")
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

    summary = ReplayHarness().build_summary(
        task=task,
        task_dir=task_dir,
        attempts=attempts,
        latest_trace=latest_trace,
    )

    assert summary["latest_attempt_id"] == f"{task.task_id}-A001"
    assert summary["stage_routes"]["rewrite_recipe"]["selected_skill"] == "rewrite_recipe"
    assert summary["dispatch_modes"]["failure_analysis"] == "read-parallel"
    assert len(summary["replay_files"]) == 5
    assert summary["report_path"] == str(task_dir / "reports" / "report.json")
