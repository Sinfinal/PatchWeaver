from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from patchweaver.api.services.overview_service import OverviewService
from patchweaver.models.attempt import AttemptRecord, FailureRecord
from patchweaver.models.task import TaskContext
from patchweaver.models.validation import ValidationItem, ValidationReport
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
    base_dir = _project_root() / ".pytest_tmp"
    base_dir.mkdir(parents=True, exist_ok=True)
    root = base_dir / f"{case_name}-{uuid4().hex[:8]}"
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_overview_service_collects_phase_three_evaluation_summaries(monkeypatch) -> None:
    tmp_path = _case_dir("overview-service")
    project_root = tmp_path / "project"
    data_dir = project_root / "data"
    workspace_root = project_root / "workspaces"
    database_path = data_dir / "patchweaver.db"
    project_root.mkdir(parents=True, exist_ok=True)
    workspace_root.mkdir(parents=True, exist_ok=True)

    challenge_dir = data_dir / "evaluations" / "challenge_dev"
    holdout_dir = data_dir / "evaluations" / "holdout"
    challenge_dir.mkdir(parents=True, exist_ok=True)
    holdout_dir.mkdir(parents=True, exist_ok=True)
    challenge_summary_path = challenge_dir / "summary.json"
    holdout_summary_path = holdout_dir / "summary.json"
    challenge_summary_path.write_text(
        json.dumps(
            {
                "fixture_name": "challenge_dev",
                "total_fixtures": 3,
                "matched_fixtures": 3,
                "missing_fixtures": 0,
                "success_count": 2,
                "success_rate": 0.6667,
                "average_attempts": 2.33,
                "failure_distribution": {"missing_fentry": 1},
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    holdout_summary_path.write_text(
        json.dumps(
            {
                "fixture_name": "holdout",
                "total_fixtures": 2,
                "matched_fixtures": 1,
                "missing_fixtures": 1,
                "success_count": 1,
                "success_rate": 1.0,
                "average_attempts": 1.0,
                "failure_distribution": {},
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    task_repo = TaskRepository(database_path)
    attempt_repo = AttemptRepository(database_path)
    artifact_repo = ArtifactRepository(database_path)

    failed_task = TaskContext(
        task_id="TASK-OVERVIEW-001",
        cve_id="CVE-2024-1086",
        target_kernel="6.6.102-5.2.an23.x86_64",
        status="failed",
        current_attempt=1,
        workspace_dir=workspace_root / "TASK-OVERVIEW-001",
    )
    built_task = TaskContext(
        task_id="TASK-OVERVIEW-002",
        cve_id="CVE-2022-0185",
        target_kernel="6.6.102-5.2.an23.x86_64",
        status="built",
        current_attempt=1,
        workspace_dir=workspace_root / "TASK-OVERVIEW-002",
    )
    task_repo.create_task(failed_task)
    task_repo.create_task(built_task)

    failed_attempt = AttemptRecord(
        task_id=failed_task.task_id,
        attempt_no=1,
        attempt_id=f"{failed_task.task_id}-A001",
        status="failed",
        failure_type="missing_fentry",
        build_log_path=failed_task.workspace_dir / "attempts" / "001" / "logs" / "build.log",
    )
    built_attempt = AttemptRecord(
        task_id=built_task.task_id,
        attempt_no=1,
        attempt_id=f"{built_task.task_id}-A001",
        status="built",
        build_log_path=built_task.workspace_dir / "attempts" / "001" / "logs" / "build.log",
        module_path=built_task.workspace_dir / "attempts" / "001" / "artifacts" / "demo.ko",
    )
    attempt_repo.create_attempt(failed_attempt)
    attempt_repo.create_attempt(built_attempt)
    attempt_repo.save_failure_record(
        FailureRecord(
            task_id=failed_task.task_id,
            attempt_id=failed_attempt.attempt_id,
            stage_name="build",
            failure_type="missing_fentry",
            summary="缺少 fentry，直接替换路径被拒绝。",
        )
    )
    attempt_repo.save_validation_report(
        built_attempt.attempt_id,
        ValidationReport(
            load_result=ValidationItem(status="passed", ok=True, detail="模块加载成功。"),
            unload_result=ValidationItem(status="passed", ok=True, detail="模块卸载成功。"),
            smoke_result=ValidationItem(status="passed", ok=True, detail="冒烟测试通过。"),
            selftest_result=ValidationItem(status="passed", ok=True, detail="自检通过。"),
            semantic_guard_result=ValidationItem(status="passed", ok=True, detail="语义守卫通过。"),
            status="passed",
            notes=["阶段测试通过。"],
        ),
    )
    artifact_repo.add_artifact(
        task_id=built_task.task_id,
        artifact_type="evaluation_summary",
        artifact_path=challenge_summary_path,
        metadata={"summary": "challenge_dev 评测摘要"},
    )

    context = SimpleNamespace(
        runtime=SimpleNamespace(
            database_path=database_path,
            data_dir=data_dir,
            project_root=project_root,
        ),
        build_config=SimpleNamespace(),
        logging_config=SimpleNamespace(
            file_path="data/logs/patchweaver.log",
            jsonl_path="data/logs/patchweaver.jsonl",
            enable_jsonl=True,
        ),
        models_config=SimpleNamespace(
            topology="single_primary_with_optional_helpers",
            default_model="qwen-plus-2025-07-28",
            development_model="qwen-plus-2025-07-28",
            delivery_model="qwen-plus-2025-07-28",
            api_key_env="PATCHWEAVER_BAILIAN_API_KEY",
            fallback_model="qwen-plus-2025-07-28",
            helper_models={
                "code_assistant": "qwen-coder-turbo-0919",
                "vision": "qwen-vl-plus-2025-05-07",
            },
        ),
        task_repo=task_repo,
        attempt_repo=attempt_repo,
        artifact_repo=artifact_repo,
    )
    service = OverviewService(context)
    service.log_service = SimpleNamespace(
        get_events=lambda limit=12: [{"kind": "task", "title": "overview", "timestamp": "2026-04-20T16:00:00"}],
        tail_logs=lambda limit=40: {
            "system_log": {"path": "system.log", "exists": True, "lines": ["system ok"]},
            "latest_build_log": {"path": "build.log", "exists": True, "lines": ["build ok"]},
            "paths": {"system_log": "system.log", "latest_build_log": "build.log"},
        },
    )
    monkeypatch.setattr(
        "patchweaver.api.services.overview_service.BuildOrchestrator.probe_environment",
        lambda self: {
            "backend": "local",
            "builder_ok": True,
            "selected_source_ok": True,
            "config_ok": True,
        },
    )
    monkeypatch.setattr(
        "patchweaver.reporter.release_service.BuildOrchestrator.probe_environment",
        lambda self: {
            "backend": "local",
            "builder_ok": True,
            "selected_source_ok": True,
            "config_ok": True,
        },
    )

    payload = service.get_overview()

    assert payload["metrics"]["total_tasks"] == 2
    assert payload["metrics"]["failed_tasks"] == 1
    assert payload["metrics"]["success_tasks"] == 1
    assert payload["metrics"]["validation_passed"] == 1
    assert payload["metrics"]["latest_evaluation_summary"] == str(challenge_summary_path)
    assert payload["metrics"]["selected_model"] == "qwen-plus-2025-07-28"
    assert [item["fixture_name"] for item in payload["evaluation_summaries"]] == ["challenge_dev", "holdout"]
    assert payload["evaluation_summaries"][0]["summary_json_path"] == str(challenge_summary_path)
    assert payload["failure_distribution"][0]["failure_type"] == "missing_fentry"
    assert payload["release"]["selected_models"]["topology"] == "single_primary_with_optional_helpers"
    assert payload["release"]["selected_models"]["helper_models"]["code_assistant"] == "qwen-coder-turbo-0919"
