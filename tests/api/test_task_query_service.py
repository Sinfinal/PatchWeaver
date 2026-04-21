from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from patchweaver.api.services.task_query_service import TaskQueryService
from patchweaver.models.attempt import AttemptRecord
from patchweaver.models.task import MachineProfile, TaskContext
from patchweaver.storage.artifact_repo import ArtifactRepository
from patchweaver.storage.attempt_repo import AttemptRepository
from patchweaver.storage.task_repo import TaskRepository


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


def test_task_query_service_detail_contains_phase_outputs() -> None:
    tmp_path = _case_dir("task-query-service")
    project_root = tmp_path / "project"
    database_path = project_root / "data" / "patchweaver.db"
    workspace_root = project_root / "workspaces"
    task_workspace = workspace_root / "TASK-DETAIL-001"
    attempt_dir = task_workspace / "attempts" / "001"
    project_root.mkdir(parents=True, exist_ok=True)
    attempt_dir.mkdir(parents=True, exist_ok=True)

    # 详情页依赖的主链产物尽量按真实目录结构落下来，这样页面和接口对的是同一份文件
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

    task_repo = TaskRepository(database_path, project_root)
    attempt_repo = AttemptRepository(database_path, project_root)
    artifact_repo = ArtifactRepository(database_path, project_root)

    task = TaskContext(
        task_id="TASK-DETAIL-001",
        cve_id="CVE-2024-1086",
        target_kernel="6.6.102-5.2.an23.x86_64",
        target_kernel_source="detected_machine",
        status="built",
        current_attempt=1,
        workspace_dir=task_workspace,
        machine_profile=MachineProfile(
            machine_system="Linux",
            machine_kernel="6.6.102-5.2.an23.x86_64",
            machine_arch="x86_64",
            build_target_kernel="6.6.102-5.2.an23.x86_64",
            build_target_kernel_source="machine_kernel",
        ),
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
        project_root=project_root,
        task_repo=task_repo,
        attempt_repo=attempt_repo,
        artifact_repo=artifact_repo,
        logging_config=SimpleNamespace(
            file_path="data/logs/patchweaver.log",
            jsonl_path="data/logs/patchweaver.jsonl",
            enable_jsonl=True,
        ),
        build_task_runner=lambda profile_name=None, max_attempts=None: _RunnerStub(),
    )

    detail = TaskQueryService(context).get_task_detail(task.task_id)

    assert detail["task"]["task_id"] == task.task_id
    assert detail["task"]["target_kernel_source"] == "detected_machine"
    assert detail["task"]["machine_profile"]["machine_kernel"] == "6.6.102-5.2.an23.x86_64"
    assert detail["latest_rewrite_plan"]["selected_recipe"] == "wrapper"
    assert detail["evaluation_summary"]["fixture_name"] == "challenge_dev"
    assert detail["replay"]["status"] == "ok"
    assert detail["attempts"][0]["planning_hints_path"].endswith("planning_hints.json")
    assert detail["report_closure"]["closure_ok"] is True
    assert any(item["stage"] == "report" and item["status"] == "completed" for item in detail["timeline"])


def test_task_query_service_create_task_uses_detected_binding_and_lazy_workspace(monkeypatch) -> None:
    tmp_path = _case_dir("task-query-create")
    project_root = tmp_path / "project"
    data_dir = project_root / "data"
    workspace_root = project_root / "workspaces"
    database_path = data_dir / "patchweaver.db"
    project_root.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    workspace_root.mkdir(parents=True, exist_ok=True)

    runtime = SimpleNamespace(
        project_root=project_root,
        workspace_root=workspace_root,
        database_path=database_path,
        profile_name="demo",
        max_attempts=3,
        default_kernel="fallback-kernel",
    )
    monkeypatch.setattr("patchweaver.api.services.task_query_service.resolve_runtime", lambda **_: runtime)
    monkeypatch.setattr(
        "patchweaver.api.services.task_query_service.resolve_task_binding",
        lambda **_: (
            "6.6.102-5.2.an23.x86_64",
            "detected_machine",
            MachineProfile(
                machine_system="Linux",
                machine_kernel="6.6.102-5.2.an23.x86_64",
                machine_arch="x86_64",
                build_target_kernel="6.6.102-5.2.an23.x86_64",
                build_target_kernel_source="machine_kernel",
            ),
        ),
    )

    context = SimpleNamespace(
        project_root=project_root,
        runtime=runtime,
        build_config=SimpleNamespace(),
        task_repo=TaskRepository(database_path, project_root),
        attempt_repo=AttemptRepository(database_path, project_root),
        artifact_repo=ArtifactRepository(database_path, project_root),
        logging_config=SimpleNamespace(
            file_path="data/logs/patchweaver.log",
            jsonl_path="data/logs/patchweaver.jsonl",
            enable_jsonl=True,
        ),
    )

    payload = TaskQueryService(context).create_task(
        cve_id="CVE-2024-1086",
        profile="demo",
        max_attempts=3,
        note="unit test",
    )

    task_workspace = project_root / payload["task"]["workspace_dir"]
    request_path = project_root / payload["request_path"]
    request_payload = json.loads(request_path.read_text(encoding="utf-8"))

    assert payload["task"]["target_kernel"] == "6.6.102-5.2.an23.x86_64"
    assert payload["task"]["target_kernel_source"] == "detected_machine"
    assert payload["task"]["machine_profile"]["machine_kernel"] == "6.6.102-5.2.an23.x86_64"
    assert task_workspace.exists()
    assert (task_workspace / "task_context.json").exists()
    assert (task_workspace / "input").exists()
    assert request_payload["target_kernel_source"] == "detected_machine"
    assert request_payload["machine_profile"]["build_target_kernel_source"] == "machine_kernel"
    assert not (task_workspace / "analysis").exists()
    assert not (task_workspace / "reports").exists()
    assert not (task_workspace / "attempts" / "001").exists()
