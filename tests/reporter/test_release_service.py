from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from patchweaver.config.models import ModelsConfig
from patchweaver.models.attempt import AttemptRecord
from patchweaver.models.task import TaskContext
from patchweaver.reporter.release_service import ReleaseService
from patchweaver.storage.artifact_repo import ArtifactRepository
from patchweaver.storage.attempt_repo import AttemptRepository
from patchweaver.storage.task_repo import TaskRepository


def test_release_service_writes_manifest_and_gate(monkeypatch, tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    data_dir = project_root / "data"
    workspace_root = project_root / "workspaces"
    docs_dir = project_root / "docs"
    manifest_dir = data_dir / "manifests"
    evaluations_dir = data_dir / "evaluations" / "challenge_dev"
    database_path = data_dir / "patchweaver.db"

    docs_dir.mkdir(parents=True, exist_ok=True)
    workspace_root.mkdir(parents=True, exist_ok=True)
    manifest_dir.mkdir(parents=True, exist_ok=True)
    evaluations_dir.mkdir(parents=True, exist_ok=True)
    (project_root / "config").mkdir(parents=True, exist_ok=True)
    (project_root / "web" / "src").mkdir(parents=True, exist_ok=True)
    (project_root / "README.md").write_text("# PatchWeaver\n", encoding="utf-8")
    (project_root / "config" / "models.yaml").write_text("provider: bailian\n", encoding="utf-8")
    (docs_dir / "PatchWeaver-总方案与创新设计总文档.md").write_text("# docs\n", encoding="utf-8")
    (manifest_dir / "doctor_report.json").write_text("{\"status\":\"ok\"}\n", encoding="utf-8")
    (project_root / "data" / "logs").mkdir(parents=True, exist_ok=True)
    (project_root / "data" / "logs" / "patchweaver.log").write_text("system ok\n", encoding="utf-8")
    (project_root / "data" / "logs" / "patchweaver.jsonl").write_text("{\"event\":\"ok\"}\n", encoding="utf-8")
    (evaluations_dir / "summary.json").write_text(
        json.dumps(
            {
                "fixture_name": "challenge_dev",
                "success_count": 1,
                "matched_fixtures": 1,
                "missing_fixtures": 0,
                "success_rate": 1.0,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (evaluations_dir / "summary.md").write_text("# summary\n", encoding="utf-8")

    task_repo = TaskRepository(database_path, project_root)
    attempt_repo = AttemptRepository(database_path, project_root)
    artifact_repo = ArtifactRepository(database_path, project_root)

    task_workspace = workspace_root / "TASK-RELEASE-001"
    attempt_dir = task_workspace / "attempts" / "001"
    (task_workspace / "reports").mkdir(parents=True, exist_ok=True)
    (attempt_dir / "logs").mkdir(parents=True, exist_ok=True)
    (attempt_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    (attempt_dir / "trace").mkdir(parents=True, exist_ok=True)
    (task_workspace / "reports" / "report.json").write_text("{\"status\":\"ok\"}\n", encoding="utf-8")
    (task_workspace / "reports" / "report.md").write_text("# report\n", encoding="utf-8")
    build_log_path = attempt_dir / "logs" / "build.log"
    build_log_path.write_text("build ok\n", encoding="utf-8")
    (attempt_dir / "artifacts" / "validation_report.json").write_text("{\"status\":\"passed\"}\n", encoding="utf-8")
    (attempt_dir / "trace" / "harness_trace.json").write_text("{\"trace_id\":\"demo\"}\n", encoding="utf-8")

    task = TaskContext(
        task_id="TASK-RELEASE-001",
        cve_id="CVE-2024-1086",
        target_kernel="6.6.102-5.2.an23.x86_64",
        status="built",
        current_attempt=1,
        workspace_dir=task_workspace,
    )
    task_repo.create_task(task)
    attempt_repo.create_attempt(
        AttemptRecord(
            task_id=task.task_id,
            attempt_no=1,
            attempt_id=f"{task.task_id}-A001",
            status="built",
            build_log_path=build_log_path,
            module_path=attempt_dir / "artifacts" / "demo.ko",
            rewritten_patch_path=attempt_dir / "rewrite" / "rewritten.patch",
        )
    )

    runtime = SimpleNamespace(
        project_root=project_root,
        data_dir=data_dir,
        workspace_root=workspace_root,
        manifest_dir=manifest_dir,
        database_path=database_path,
        profile_name="full",
        default_kernel="6.6.102-5.2.an23.x86_64",
    )
    build_config = SimpleNamespace()
    logging_config = SimpleNamespace(
        file_path="data/logs/patchweaver.log",
        jsonl_path="data/logs/patchweaver.jsonl",
        enable_jsonl=True,
    )
    models_config = ModelsConfig()

    monkeypatch.setenv("PATCHWEAVER_BAILIAN_API_KEY", "demo-key")
    monkeypatch.setattr(
        "patchweaver.reporter.release_service.BuildOrchestrator.probe_environment",
        lambda self: {
            "backend": "local",
            "builder_ok": True,
            "selected_source_ok": True,
            "config_ok": True,
            "selected_source_dir": "/opt/kernel-src",
        },
    )

    service = ReleaseService(
        runtime=runtime,
        build_config=build_config,
        logging_config=logging_config,
        models_config=models_config,
        task_repo=task_repo,
        attempt_repo=attempt_repo,
        artifact_repo=artifact_repo,
    )

    manifest_payload = service.prepare_submission()
    gate_payload = service.run_gate()

    assert (project_root / manifest_payload["final_manifest_json"]).exists()
    assert (project_root / gate_payload["final_gate_json"]).exists()
    assert gate_payload["status"] == "passed"
    assert any(item["goal"] == "输出结构化报告、日志和产物" for item in gate_payload["goal_check"])
    manifest_json = json.loads((project_root / manifest_payload["final_manifest_json"]).read_text(encoding="utf-8"))
    assert manifest_json["models"]["topology"] == "single_primary_with_optional_helpers"
    assert any(item["name"] == "PatchWeaver-模型选型说明.md" for item in manifest_json["documents"])


def test_release_service_accepts_representative_metrics_as_evaluation_summary(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    data_dir = project_root / "data"
    workspace_root = project_root / "workspaces"
    metrics_dir = data_dir / "evaluations" / "validation_v0509"
    database_path = data_dir / "patchweaver.db"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    workspace_root.mkdir(parents=True, exist_ok=True)
    (metrics_dir / "representative_metrics_v0510.json").write_text(
        json.dumps(
            {
                "metrics": {
                    "representative_total": 10,
                    "representative_success_count": 10,
                    "representative_success_rate": 1.0,
                    "average_attempts": 1.0,
                },
                "evidence_summary": {"ko": {"passed": 10, "total": 10}},
                "failure_buckets": {"success": 10},
                "target_gap": {"explanation": "代表集达到目标。"},
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    service = ReleaseService(
        runtime=SimpleNamespace(
            project_root=project_root,
            data_dir=data_dir,
            workspace_root=workspace_root,
            manifest_dir=data_dir / "manifests",
            database_path=database_path,
            profile_name="full",
            default_kernel="6.6.102-5.2.an23.x86_64",
        ),
        build_config=SimpleNamespace(),
        logging_config=SimpleNamespace(
            file_path="data/logs/patchweaver.log",
            jsonl_path="data/logs/patchweaver.jsonl",
            enable_jsonl=True,
        ),
        models_config=ModelsConfig(),
        task_repo=TaskRepository(database_path, project_root),
        attempt_repo=AttemptRepository(database_path, project_root),
        artifact_repo=ArtifactRepository(database_path, project_root),
    )

    summaries = service._evaluation_summaries()

    assert summaries == [
        {
            "fixture_name": "validation_v0509/representative_metrics_v0510",
            "success_count": 10,
            "matched_fixtures": 10,
            "missing_fixtures": 0,
            "success_rate": 1.0,
            "bucket_order": ["success"],
            "bucket_counts": {"success": 10},
            "bucket_summary": {"ko": {"passed": 10, "total": 10}},
            "mixed_summary_note": "代表集达到目标。",
            "summary_json_path": "data/evaluations/validation_v0509/representative_metrics_v0510.json",
            "summary_md_path": "data/evaluations/validation_v0509/representative_metrics_v0510.md",
        }
    ]


def test_release_service_accepts_full_run_result_as_evaluation_summary(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    data_dir = project_root / "data"
    workspace_root = project_root / "workspaces"
    validation_dir = data_dir / "evaluations" / "validation_v0509"
    database_path = data_dir / "patchweaver.db"
    validation_dir.mkdir(parents=True, exist_ok=True)
    workspace_root.mkdir(parents=True, exist_ok=True)
    (validation_dir / "final_holdout10_full_run_v0509.json").write_text(
        json.dumps(
            {
                "summary": {
                    "total_cases": 10,
                    "representative_total": 10,
                    "representative_success_rate": 1.0,
                    "average_attempts": 1.0,
                    "bucket_counts": {"buildable_and_should_pass": 10},
                    "current_positive_pool_size": 12,
                    "positive_pool_gap": 0,
                }
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    service = ReleaseService(
        runtime=SimpleNamespace(
            project_root=project_root,
            data_dir=data_dir,
            workspace_root=workspace_root,
            manifest_dir=data_dir / "manifests",
            database_path=database_path,
            profile_name="full",
            default_kernel="6.6.102-5.2.an23.x86_64",
        ),
        build_config=SimpleNamespace(),
        logging_config=SimpleNamespace(
            file_path="data/logs/patchweaver.log",
            jsonl_path="data/logs/patchweaver.jsonl",
            enable_jsonl=True,
        ),
        models_config=ModelsConfig(),
        task_repo=TaskRepository(database_path, project_root),
        attempt_repo=AttemptRepository(database_path, project_root),
        artifact_repo=ArtifactRepository(database_path, project_root),
    )

    summaries = service._evaluation_summaries()

    assert summaries[0]["fixture_name"] == "validation_v0509/final_holdout10_full_run_v0509"
    assert summaries[0]["success_count"] == 10
    assert summaries[0]["matched_fixtures"] == 10
    assert summaries[0]["success_rate"] == 1.0
    assert summaries[0]["summary_json_path"] == "data/evaluations/validation_v0509/final_holdout10_full_run_v0509.json"


def test_release_service_accepts_legacy_full_run_total_cases_only(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    data_dir = project_root / "data"
    workspace_root = project_root / "workspaces"
    validation_dir = data_dir / "evaluations" / "review_v0510"
    database_path = data_dir / "patchweaver.db"
    validation_dir.mkdir(parents=True, exist_ok=True)
    workspace_root.mkdir(parents=True, exist_ok=True)
    (validation_dir / "review_complex2_full.json").write_text(
        json.dumps(
            {
                "summary": {
                    "total_cases": 2,
                    "representative_success_rate": 1.0,
                    "average_attempts": 1.0,
                    "bucket_counts": {"buildable_and_should_pass": 2},
                    "current_positive_pool_size": 12,
                    "positive_pool_gap": 0,
                }
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    service = ReleaseService(
        runtime=SimpleNamespace(
            project_root=project_root,
            data_dir=data_dir,
            workspace_root=workspace_root,
            manifest_dir=data_dir / "manifests",
            database_path=database_path,
            profile_name="full",
            default_kernel="6.6.102-5.2.an23.x86_64",
        ),
        build_config=SimpleNamespace(),
        logging_config=SimpleNamespace(
            file_path="data/logs/patchweaver.log",
            jsonl_path="data/logs/patchweaver.jsonl",
            enable_jsonl=True,
        ),
        models_config=ModelsConfig(),
        task_repo=TaskRepository(database_path, project_root),
        attempt_repo=AttemptRepository(database_path, project_root),
        artifact_repo=ArtifactRepository(database_path, project_root),
    )

    summaries = service._evaluation_summaries()

    assert summaries[0]["fixture_name"] == "review_v0510/review_complex2_full"
    assert summaries[0]["success_count"] == 2
    assert summaries[0]["matched_fixtures"] == 2
    assert summaries[0]["success_rate"] == 1.0
