from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from patchweaver.api.app import create_app
from patchweaver.api.deps import get_api_context
from patchweaver.api.services.report_query_service import ReportQueryService
from patchweaver.api.services.task_query_service import TaskQueryService
from patchweaver.models.attempt import AttemptRecord, FailureRecord
from patchweaver.models.task import MachineProfile, TaskContext
from patchweaver.storage.artifact_repo import ArtifactRepository
from patchweaver.storage.attempt_repo import AttemptRepository
from patchweaver.storage.task_repo import TaskRepository


def test_task_query_service_agent_decision_summary_reads_workspace_reports(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    database_path = project_root / "data" / "patchweaver.db"
    workspace_root = project_root / "workspaces"
    task_workspace = workspace_root / "TASK-DECISION-001"
    attempt_dir = task_workspace / "attempts" / "001"
    (task_workspace / "analysis").mkdir(parents=True, exist_ok=True)
    (task_workspace / "reports").mkdir(parents=True, exist_ok=True)
    (attempt_dir / "logs").mkdir(parents=True, exist_ok=True)
    (attempt_dir / "rewrite").mkdir(parents=True, exist_ok=True)
    (attempt_dir / "artifacts").mkdir(parents=True, exist_ok=True)

    (task_workspace / "analysis" / "repair_intent.json").write_text(
        json.dumps(
            {
                "cve_id": "CVE-2026-0001",
                "bug_class": "bounds_check",
                "root_cause": "missing length guard",
                "vulnerability_conditions": ["len > buf_size"],
                "guard_conditions": ["if (len > buf_size) return -EINVAL;"],
                "guard_sites": ["drivers/demo.c:demo_write"],
                "safe_exits": ["return -EINVAL"],
                "preserved_side_effects": ["keep audit log"],
                "touched_files": ["drivers/demo.c"],
                "touched_functions": ["demo_write"],
                "recommended_strategy": "semantic_guard",
                "confidence": 0.82,
                "evidence": ["added guard in upstream fix"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (attempt_dir / "rewrite" / "rewrite_plan.json").write_text(
        json.dumps(
            {
                "selected_recipe": "smpl_primary_rewrite",
                "selected_strategy": "smpl_template",
                "selection_reason": "semantic guard 需要模板化落点，切换到 SmPL 路线。",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (attempt_dir / "logs" / "failure_record.json").write_text(
        json.dumps(
            {
                "task_id": "TASK-DECISION-001",
                "attempt_id": "TASK-DECISION-001-A001",
                "stage_name": "build",
                "failure_type": "compile_failed",
                "summary": "demo_write references missing field",
                "agent_next_action": "补齐目标内核结构体字段差异后重试 SmPL 路线。",
                "diagnostic_details": {
                    "compiler_error": "struct demo has no member named limit",
                    "log_excerpt": ["error: no member named limit"],
                },
                "evidence": ["build.log:error: no member named limit"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (attempt_dir / "artifacts" / "build_summary.json").write_text(
        json.dumps(
            {
                "status": "failed",
                "failure_type": "compile_failed",
                "build_exec_status": "executed",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (task_workspace / "reports" / "report.json").write_text(
        json.dumps({"final_status": "failed", "selected_recipe": "fallback_recipe"}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (task_workspace / "reports" / "report.md").write_text("# failed\n", encoding="utf-8")
    (task_workspace / "reports" / "evaluation_summary.json").write_text("{\"latest_status\":\"failed\"}\n", encoding="utf-8")

    task_repo = TaskRepository(database_path, project_root)
    attempt_repo = AttemptRepository(database_path, project_root)
    artifact_repo = ArtifactRepository(database_path, project_root)
    task = TaskContext(
        task_id="TASK-DECISION-001",
        cve_id="CVE-2026-0001",
        target_kernel="6.6.102-5.2.an23.x86_64",
        target_kernel_source="detected_machine",
        status="failed",
        current_attempt=1,
        max_attempts=3,
        workspace_dir=task_workspace,
    )
    task_repo.create_task(task)
    attempt_repo.create_attempt(
        AttemptRecord(
            task_id=task.task_id,
            attempt_no=1,
            attempt_id="TASK-DECISION-001-A001",
            status="failed",
            failure_type="compile_failed",
            build_exec_status="executed",
        )
    )

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
        build_task_runner=lambda profile_name=None, max_attempts=None: SimpleNamespace(
            replay_task=lambda task_id: {
                "task_id": task_id,
                "status": "ok",
                "stage_routes": {},
                "dispatch_modes": {},
                "replay_files": [],
                "comparison": {},
            }
        ),
    )

    summary = TaskQueryService(context).get_agent_decision_summary(task.task_id)
    report = ReportQueryService(context).get_task_report(task.task_id)

    assert summary["repair_intent"]["recommended_strategy"] == "semantic_guard"
    assert summary["repair_intent"]["guard_conditions"] == ["if (len > buf_size) return -EINVAL;"]
    assert summary["selected_recipe"] == "smpl_primary_rewrite"
    assert summary["selected_strategy"] == "smpl_template"
    assert summary["strategy"] == "smpl_template"
    assert summary["strategy_switch"]["switched"] is True
    assert summary["failure_type"] == "compile_failed"
    assert summary["agent_next_action"] == "补齐目标内核结构体字段差异后重试 SmPL 路线。"
    assert summary["diagnostic_details"]["compiler_error"] == "struct demo has no member named limit"
    assert summary["failure_record"]["raw"]["summary"] == "demo_write references missing field"
    assert summary["source_exists"]["repair_intent"] is True
    assert summary["source_exists"]["failure_record"] is True
    assert report["agent_decision_summary"]["selected_recipe"] == "smpl_primary_rewrite"
    assert report["agent_decision_summary"]["failure_type"] == "compile_failed"


def test_agent_decision_endpoint_returns_workspace_summary(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    database_path = project_root / "data" / "patchweaver.db"
    task_workspace = project_root / "workspaces" / "TASK-DECISION-API"
    attempt_dir = task_workspace / "attempts" / "001"
    (task_workspace / "analysis").mkdir(parents=True, exist_ok=True)
    (task_workspace / "reports").mkdir(parents=True, exist_ok=True)
    (attempt_dir / "logs").mkdir(parents=True, exist_ok=True)
    (attempt_dir / "rewrite").mkdir(parents=True, exist_ok=True)
    (attempt_dir / "artifacts").mkdir(parents=True, exist_ok=True)

    (task_workspace / "analysis" / "repair_intent.json").write_text(
        json.dumps({"cve_id": "CVE-2026-0002", "recommended_strategy": "callback_shadow"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (attempt_dir / "rewrite" / "rewrite_plan.json").write_text(
        json.dumps({"selected_recipe": "callback_shadow_wrap", "selected_strategy": "callback_shadow"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (attempt_dir / "logs" / "failure_record.json").write_text(
        json.dumps(
            {
                "failure_type": "kpatch_constraint",
                "summary": "unsupported section change",
                "diagnostics": {"constraint": "section .init.text changed"},
                "agent_next_action": "切换 section avoidance 或收口为不可热补丁化。",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    task_repo = TaskRepository(database_path, project_root)
    attempt_repo = AttemptRepository(database_path, project_root)
    artifact_repo = ArtifactRepository(database_path, project_root)
    task_repo.create_task(
        TaskContext(
            task_id="TASK-DECISION-API",
            cve_id="CVE-2026-0002",
            target_kernel="6.6.102-5.2.an23.x86_64",
            status="failed",
            current_attempt=1,
            workspace_dir=task_workspace,
        )
    )
    attempt_repo.create_attempt(
        AttemptRecord(
            task_id="TASK-DECISION-API",
            attempt_no=1,
            attempt_id="TASK-DECISION-API-A001",
            status="failed",
            failure_type="kpatch_constraint",
        )
    )
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
    )
    app = create_app()
    app.dependency_overrides[get_api_context] = lambda: context
    try:
        response = TestClient(app).get("/api/v1/tasks/TASK-DECISION-API/agent-decision")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["repair_intent"]["recommended_strategy"] == "callback_shadow"
    assert payload["selected_recipe"] == "callback_shadow_wrap"
    assert payload["failure_type"] == "kpatch_constraint"
    assert payload["diagnostic_details"]["constraint"] == "section .init.text changed"
    assert payload["agent_next_action"] == "切换 section avoidance 或收口为不可热补丁化。"


def test_task_query_service_detail_contains_phase_outputs(tmp_path: Path) -> None:
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
        build_exec_status="executed",
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
        "latest_failure_type": attempt.failure_type,
        "latest_build_exec_status": attempt.build_exec_status,
        "latest_target_state": attempt.target_state,
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
    assert detail["task"]["latest_build_exec_status"] == "executed"
    assert detail["latest_rewrite_plan"]["selected_recipe"] == "wrapper"
    assert detail["evaluation_summary"]["fixture_name"] == "challenge_dev"
    assert detail["replay"]["status"] == "ok"
    assert detail["replay"]["latest_build_exec_status"] == "executed"
    assert detail["attempts"][0]["build_exec_status"] == "executed"
    assert detail["attempts"][0]["planning_hints_path"].endswith("planning_hints.json")
    assert detail["process_summary"]["overall_status"] == "success"
    assert detail["process_summary"]["headline"] == "热补丁已构建并通过验证"
    assert any(item["stage"] == "build" and item["status"] == "success" for item in detail["stage_view"])
    assert any(item["stage"] == "validate" and item["status"] == "success" for item in detail["stage_view"])
    assert detail["report_closure"]["closure_ok"] is True
    assert any(item["stage"] == "report" and item["status"] == "completed" for item in detail["timeline"])


def test_task_query_service_create_task_uses_detected_binding_and_lazy_workspace(monkeypatch, tmp_path: Path) -> None:
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

    assert payload["status"] == "ok"
    assert payload["created"] is True
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


def test_task_query_service_list_tasks_supports_extended_filters_and_fixture_group(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    data_dir = project_root / "data"
    workspace_root = project_root / "workspaces"
    fixtures_dir = project_root / "evaluations" / "fixtures"
    database_path = data_dir / "patchweaver.db"
    project_root.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    workspace_root.mkdir(parents=True, exist_ok=True)
    fixtures_dir.mkdir(parents=True, exist_ok=True)

    (fixtures_dir / "challenge_dev.json").write_text(
        json.dumps(
            [
                {
                    "fixture_id": "fixture-1086",
                    "fixture_group": "challenge_dev",
                    "cve_id": "CVE-2024-1086",
                    "target_kernel": "6.6.102-5.2.an23.x86_64",
                }
            ],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (fixtures_dir / "holdout.json").write_text(
        json.dumps(
            [
                {
                    "fixture_id": "fixture-0185",
                    "fixture_group": "holdout",
                    "cve_id": "CVE-2022-0185",
                    "target_kernel": "6.6.102-5.2.an23.x86_64",
                }
            ],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    task_repo = TaskRepository(database_path, project_root)
    attempt_repo = AttemptRepository(database_path, project_root)
    artifact_repo = ArtifactRepository(database_path, project_root)

    task_one = TaskContext(
        task_id="TASK-FILTER-001",
        cve_id="CVE-2024-1086",
        target_kernel="6.6.102-5.2.an23.x86_64",
        target_kernel_source="detected_build_env",
        status="failed",
        current_attempt=1,
        max_attempts=3,
        workspace_dir=workspace_root / "TASK-FILTER-001",
        created_at="2026-04-21T12:00:00",
        updated_at="2026-04-21T12:10:00",
    )
    task_two = TaskContext(
        task_id="TASK-FILTER-002",
        cve_id="CVE-2022-0185",
        target_kernel="6.6.102-5.2.an23.x86_64",
        target_kernel_source="detected_build_env",
        status="built",
        current_attempt=2,
        max_attempts=3,
        workspace_dir=workspace_root / "TASK-FILTER-002",
        created_at="2026-04-21T13:00:00",
        updated_at="2026-04-21T13:10:00",
    )
    task_repo.create_task(task_one)
    task_repo.create_task(task_two)

    attempt_one = AttemptRecord(
        task_id=task_one.task_id,
        attempt_no=1,
        attempt_id="TASK-FILTER-001-A001",
        status="failed",
        failure_type="target_already_patched",
        build_exec_status="not_run",
        target_state="target_already_patched",
    )
    attempt_two = AttemptRecord(
        task_id=task_two.task_id,
        attempt_no=1,
        attempt_id="TASK-FILTER-002-A001",
        status="built",
        build_exec_status="executed",
    )
    attempt_repo.create_attempt(attempt_one)
    attempt_repo.create_attempt(attempt_two)
    attempt_one_dir = task_one.workspace_dir / "attempts" / "001"
    (attempt_one_dir / "logs").mkdir(parents=True, exist_ok=True)
    (attempt_one_dir / "rewrite").mkdir(parents=True, exist_ok=True)
    (attempt_one_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    (task_one.workspace_dir / "reports").mkdir(parents=True, exist_ok=True)
    (task_one.workspace_dir / "task_context.json").write_text("{\"task_id\":\"TASK-FILTER-001\"}\n", encoding="utf-8")
    (attempt_one_dir / "logs" / "failure_record.json").write_text(
        json.dumps(
            {
                "task_id": task_one.task_id,
                "attempt_id": attempt_one.attempt_id,
                "stage_name": "build",
                "failure_type": "target_already_patched",
                "summary": "目标源码已修复",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (attempt_one_dir / "rewrite" / "apply_precheck.json").write_text(
        json.dumps(
            {
                "failure_type": "target_already_patched",
                "build_exec_status": "not_run",
                "target_state": "target_already_patched",
                "summary": "目标源码已包含该补丁",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (attempt_one_dir / "artifacts" / "build_summary.json").write_text(
        json.dumps(
            {
                "status": "failed",
                "failure_type": "patch_apply_failed",
                "build_exec_status": "not_run",
                "summary": "历史构建摘要仍保留旧失败类型",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    attempt_repo.save_failure_record(
        FailureRecord(
            task_id=task_one.task_id,
            attempt_id=attempt_one.attempt_id,
            stage_name="build",
            failure_type="target_already_patched",
            summary="目标源码已修复",
        )
    )

    class _RunnerStub:
        def replay_task(self, task_id: str) -> dict[str, object]:
            return {"task_id": task_id, "status": "empty", "stage_routes": {}, "dispatch_modes": {}, "replay_files": [], "comparison": {}}

    context = SimpleNamespace(
        project_root=project_root,
        runtime=SimpleNamespace(database_path=database_path),
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
    service = TaskQueryService(context)

    challenge_items = service.list_tasks(fixture_group="challenge_dev")["items"]
    executed_items = service.list_tasks(build_exec_status="executed")["items"]
    target_state_items = service.list_tasks(target_state="target_already_patched")["items"]
    current_attempt_items = service.list_tasks(current_attempt=2)["items"]
    created_after_items = service.list_tasks(created_at_from="2026-04-21T12:30:00")["items"]
    detail = service.get_task_detail(task_one.task_id)

    assert [item["task_id"] for item in challenge_items] == [task_one.task_id]
    assert challenge_items[0]["fixture_group"] == "challenge_dev"
    assert challenge_items[0]["fixture_id"] == "fixture-1086"
    assert [item["task_id"] for item in executed_items] == [task_two.task_id]
    assert [item["task_id"] for item in target_state_items] == [task_one.task_id]
    assert [item["task_id"] for item in current_attempt_items] == [task_two.task_id]
    assert [item["task_id"] for item in created_after_items] == [task_two.task_id]
    assert detail["task"]["fixture_group"] == "challenge_dev"
    assert detail["task"]["fixture_id"] == "fixture-1086"
    assert detail["process_summary"]["headline"] == "目标已修复 / 构建未执行"
    assert detail["process_summary"]["latest_failure_type"] == "target_already_patched"
    assert "build_summary=patch_apply_failed" in detail["process_summary"]["state_conflicts"]
    assert any(item["stage"] == "build" and item["status"] == "skipped" for item in detail["stage_view"])
    assert any(item["stage"] == "validate" and item["status"] == "skipped" for item in detail["stage_view"])


def test_task_query_service_create_task_blocks_duplicate_already_fixed_task(monkeypatch, tmp_path: Path) -> None:
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
    machine_profile = MachineProfile(
        machine_system="Linux",
        machine_kernel="6.6.102-5.2.an23.x86_64",
        machine_arch="x86_64",
        build_target_kernel="6.6.102-5.2.an23.x86_64",
        build_target_kernel_source="machine_kernel",
        selected_source_dir="/root/kernel-src-clean",
    )
    monkeypatch.setattr("patchweaver.api.services.task_query_service.resolve_runtime", lambda **_: runtime)
    monkeypatch.setattr(
        "patchweaver.api.services.task_query_service.resolve_task_binding",
        lambda **_: ("6.6.102-5.2.an23.x86_64", "detected_machine", machine_profile),
    )

    task_repo = TaskRepository(database_path, project_root)
    attempt_repo = AttemptRepository(database_path, project_root)
    artifact_repo = ArtifactRepository(database_path, project_root)
    existing_task = TaskContext(
        task_id="TASK-DUP-001",
        cve_id="CVE-2022-0185",
        target_kernel="6.6.102-5.2.an23.x86_64",
        target_kernel_source="detected_machine",
        profile_name="demo",
        status="target_state",
        current_attempt=1,
        max_attempts=3,
        workspace_dir=workspace_root / "TASK-DUP-001",
        machine_profile=machine_profile,
    )
    task_repo.create_task(existing_task)
    attempt_repo.create_attempt(
        AttemptRecord(
            task_id=existing_task.task_id,
            attempt_no=1,
            attempt_id="TASK-DUP-001-A001",
            status="target_state",
            failure_type="target_already_patched",
            build_exec_status="not_run",
            target_state="target_already_patched",
        )
    )

    context = SimpleNamespace(
        project_root=project_root,
        runtime=runtime,
        build_config=SimpleNamespace(),
        task_repo=task_repo,
        attempt_repo=attempt_repo,
        artifact_repo=artifact_repo,
        logging_config=SimpleNamespace(
            file_path="data/logs/patchweaver.log",
            jsonl_path="data/logs/patchweaver.jsonl",
            enable_jsonl=True,
        ),
    )

    payload = TaskQueryService(context).create_task(
        cve_id="CVE-2022-0185",
        profile="demo",
        max_attempts=3,
    )

    assert payload["status"] == "duplicate"
    assert payload["created"] is False
    assert payload["reason"] == "target_already_patched"
    assert payload["decision"] == "skip_already_fixed"
    assert payload["existing_task"]["task_id"] == existing_task.task_id
    assert payload["existing_task"]["latest_target_state"] == "target_already_patched"
    assert payload["duplicate_scope"]["selected_source_dir"] == "/root/kernel-src-clean"
    assert task_repo.list_tasks(limit=10)[0].task_id == existing_task.task_id


def test_task_query_service_create_task_allows_force_new_on_duplicate(monkeypatch, tmp_path: Path) -> None:
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
    machine_profile = MachineProfile(
        machine_system="Linux",
        machine_kernel="6.6.102-5.2.an23.x86_64",
        machine_arch="x86_64",
        build_target_kernel="6.6.102-5.2.an23.x86_64",
        build_target_kernel_source="machine_kernel",
        selected_source_dir="/root/kernel-src-clean",
    )
    monkeypatch.setattr("patchweaver.api.services.task_query_service.resolve_runtime", lambda **_: runtime)
    monkeypatch.setattr(
        "patchweaver.api.services.task_query_service.resolve_task_binding",
        lambda **_: ("6.6.102-5.2.an23.x86_64", "detected_machine", machine_profile),
    )

    task_repo = TaskRepository(database_path, project_root)
    task_repo.create_task(
        TaskContext(
            task_id="TASK-DUP-002",
            cve_id="CVE-2024-1086",
            target_kernel="6.6.102-5.2.an23.x86_64",
            target_kernel_source="detected_machine",
            profile_name="demo",
            status="failed",
            current_attempt=1,
            max_attempts=3,
            workspace_dir=workspace_root / "TASK-DUP-002",
            machine_profile=machine_profile,
        )
    )

    context = SimpleNamespace(
        project_root=project_root,
        runtime=runtime,
        build_config=SimpleNamespace(),
        task_repo=task_repo,
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
        force_new=True,
    )

    task_ids = [item.task_id for item in task_repo.list_tasks(limit=10)]

    assert payload["status"] == "ok"
    assert payload["created"] is True
    assert payload["task"]["task_id"] != "TASK-DUP-002"
    assert payload["task"]["task_id"] in task_ids
