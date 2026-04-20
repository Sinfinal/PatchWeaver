from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from patchweaver.api.services.task_query_service import TaskQueryService
from patchweaver.models.attempt import AttemptRecord
from patchweaver.models.task import TaskContext
from patchweaver.storage.artifact_repo import ArtifactRepository
from patchweaver.storage.attempt_repo import AttemptRepository
from patchweaver.storage.task_repo import TaskRepository


def _case_dir(case_name: str) -> Path:
    base_dir = Path("E:/Desk/patchweaver_pytest_cases")
    base_dir.mkdir(parents=True, exist_ok=True)
    root = base_dir / f"{case_name}-{uuid4().hex[:8]}"
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_task_query_service_detail_contains_phase_outputs() -> None:
    tmp_path = _case_dir("task-query-service")
    project_root = tmp_path / "project"
    database_path = project_root / "data" / "patchweaver.db"
    workspace_root = project_root / "workspaces"
    task_workspace = workspace_root / "TASK-DETAIL-001"
    attempt_dir = task_workspace / "attempts" / "001"
    project_root.mkdir(parents=True, exist_ok=True)
    attempt_dir.mkdir(parents=True, exist_ok=True)

    # 详情页依赖的主链产物尽量按真实目录结构落下来，这样页面和接口对的是同一份文件。
    (task_workspace / "analysis" / "context").mkdir(parents=True, exist_ok=True)
    (task_workspace / "analysis" / "trace").mkdir(parents=True, exist_ok=True)
    (task_workspace / "input").mkdir(parents=True, exist_ok=True)
    (task_workspace / "reports").mkdir(parents=True, exist_ok=True)
    (attempt_dir / "logs").mkdir(parents=True, exist_ok=True)
    (attempt_dir / "rewrite").mkdir(parents=True, exist_ok=True)
    (attempt_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    (attempt_dir / "trace").mkdir(parents=True, exist_ok=True)

    patch_bundle_path = task_workspace / "input" / "patch_bundle.json"
    patch_bundle_path.write_text(
        json.dumps({"cve_id": "CVE-2024-1086", "commit_message": "demo"}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (task_workspace / "analysis" / "semantic_card.json").write_text("{\"root_cause\":\"demo\"}\n", encoding="utf-8")
    (task_workspace / "analysis" / "constraint_report.json").write_text("{\"high_risk_count\":1}\n", encoding="utf-8")
    (task_workspace / "analysis" / "context" / "context_bundle.json").write_text("{\"notes\":[]}\n", encoding="utf-8")
    (task_workspace / "analysis" / "trace" / "analysis_trace.json").write_text("{\"trace_id\":\"analysis\"}\n", encoding="utf-8")
    (task_workspace / "reports" / "report.json").write_text("{\"status\":\"ok\"}\n", encoding="utf-8")
    (task_workspace / "reports" / "report.md").write_text("# report\n", encoding="utf-8")
    (task_workspace / "reports" / "evaluation_summary.json").write_text(
        json.dumps({"fixture_name": "challenge_dev", "success_rate": 0.5}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (task_workspace / "task_context.json").write_text("{\"task_id\":\"TASK-DETAIL-001\"}\n", encoding="utf-8")

    build_log_path = attempt_dir / "logs" / "build.log"
    build_log_path.write_text("build ok\n", encoding="utf-8")
    (attempt_dir / "logs" / "failure_record.json").write_text("{\"failure_type\":\"none\"}\n", encoding="utf-8")
    (attempt_dir / "rewrite" / "rewrite_plan.json").write_text("{\"selected_recipe\":\"wrapper\"}\n", encoding="utf-8")
    (attempt_dir / "rewrite" / "planning_hints.json").write_text("{\"risk_types\":[\"missing_fentry\"]}\n", encoding="utf-8")
    (attempt_dir / "artifacts" / "validation_report.json").write_text("{\"status\":\"passed\"}\n", encoding="utf-8")
    (attempt_dir / "artifacts" / "validation_matrix.json").write_text("[]\n", encoding="utf-8")
    (attempt_dir / "artifacts" / "semantic_guard.json").write_text("{\"status\":\"passed\"}\n", encoding="utf-8")
    (attempt_dir / "trace" / "harness_trace.json").write_text("{\"trace_id\":\"attempt\"}\n", encoding="utf-8")

    task_repo = TaskRepository(database_path)
    attempt_repo = AttemptRepository(database_path)
    artifact_repo = ArtifactRepository(database_path)

    task = TaskContext(
        task_id="TASK-DETAIL-001",
        cve_id="CVE-2024-1086",
        target_kernel="6.6.102-5.2.an23.x86_64",
        status="built",
        current_attempt=1,
        workspace_dir=task_workspace,
    )
    task_repo.create_task(task)
    attempt = AttemptRecord(
        task_id=task.task_id,
        attempt_no=1,
        attempt_id=f"{task.task_id}-A001",
        status="built",
        build_log_path=build_log_path,
        module_path=attempt_dir / "artifacts" / "demo_patch.ko",
        rewritten_patch_path=attempt_dir / "rewrite" / "rewritten.patch",
    )
    attempt_repo.create_attempt(attempt)

    for artifact_type, artifact_path in [
        ("patch_bundle", patch_bundle_path),
        ("analysis_trace", task_workspace / "analysis" / "trace" / "analysis_trace.json"),
        ("final_report_json", task_workspace / "reports" / "report.json"),
        ("evaluation_summary", task_workspace / "reports" / "evaluation_summary.json"),
        ("rewrite_plan", attempt_dir / "rewrite" / "rewrite_plan.json"),
        ("planning_hints", attempt_dir / "rewrite" / "planning_hints.json"),
        ("validation_report", attempt_dir / "artifacts" / "validation_report.json"),
        ("harness_trace", attempt_dir / "trace" / "harness_trace.json"),
    ]:
        artifact_repo.add_artifact(
            task_id=task.task_id,
            attempt_id=attempt.attempt_id if "rewrite" in artifact_type or "validation" in artifact_type or "trace" in artifact_type else None,
            artifact_type=artifact_type,
            artifact_path=artifact_path,
            metadata={"summary": artifact_type},
        )

    replay_payload = {
        "command": "replay",
        "task_id": task.task_id,
        "latest_attempt_id": attempt.attempt_id,
        "latest_attempt_status": attempt.status,
        "trace_path": str(attempt_dir / "trace" / "harness_trace.json"),
        "report_path": str(task_workspace / "reports" / "report.json"),
        "evaluation_summary_path": str(task_workspace / "reports" / "evaluation_summary.json"),
        "stage_routes": {},
        "dispatch_modes": {},
        "replay_files": [],
        "comparison": {"attempt_count": 1},
        "status": "ok",
    }

    class _RunnerStub:
        def replay_task(self, task_id: str) -> dict[str, object]:
            return replay_payload

    context = SimpleNamespace(
        task_repo=task_repo,
        attempt_repo=attempt_repo,
        artifact_repo=artifact_repo,
        build_task_runner=lambda profile_name=None, max_attempts=None: _RunnerStub(),
    )

    detail = TaskQueryService(context).get_task_detail(task.task_id)

    assert detail["task"]["task_id"] == task.task_id
    assert detail["latest_rewrite_plan"]["selected_recipe"] == "wrapper"
    assert detail["evaluation_summary"]["fixture_name"] == "challenge_dev"
    assert detail["replay"]["status"] == "ok"
    assert detail["attempts"][0]["planning_hints_path"].endswith("planning_hints.json")
    assert any(item["stage"] == "report" and item["status"] == "completed" for item in detail["timeline"])
