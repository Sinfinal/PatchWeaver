from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from patchweaver.api.services.report_query_service import ReportQueryService


def test_report_query_service_reads_bucket_summary(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    evaluations_dir = project_root / "data" / "evaluations" / "challenge_dev"
    evaluations_dir.mkdir(parents=True, exist_ok=True)

    summary_path = evaluations_dir / "summary.json"
    summary_md_path = evaluations_dir / "summary.md"
    summary_path.write_text(
        json.dumps(
            {
                "fixture_name": "challenge_dev",
                "total_fixtures": 2,
                "matched_fixtures": 2,
                "missing_fixtures": 0,
                "success_count": 1,
                "success_rate": 0.5,
                "average_attempts": 1.5,
                "bucket_order": ["already_patched", "buildable_and_should_pass"],
                "bucket_counts": {
                    "already_patched": 1,
                    "buildable_and_should_pass": 1,
                },
                "bucket_summary": {
                    "already_patched": {
                        "label": "目标已修复类",
                        "primary_metric": {
                            "label": "目标态识别率",
                            "display_value": "100.00%",
                        },
                    }
                },
                "fixtures": [
                    {
                        "fixture_id": "fixture-1086",
                        "fixture_group": "challenge_dev",
                        "sample_bucket": "already_patched",
                        "task_id": "TASK-001",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    summary_md_path.write_text("# summary\n", encoding="utf-8")
    (evaluations_dir / "fixture-1086.json").write_text("{\"fixture_id\":\"fixture-1086\"}\n", encoding="utf-8")

    context = SimpleNamespace(
        project_root=project_root,
        runtime=SimpleNamespace(data_dir=project_root / "data"),
        logging_config=SimpleNamespace(
            file_path="data/logs/patchweaver.log",
            jsonl_path="data/logs/patchweaver.jsonl",
            enable_jsonl=True,
        ),
    )
    service = ReportQueryService(context)

    groups = service.list_evaluation_groups()
    detail = service.get_group_summary("challenge_dev")

    assert groups["items"][0]["bucket_order"] == ["already_patched", "buildable_and_should_pass"]
    assert groups["items"][0]["bucket_summary"]["already_patched"]["label"] == "目标已修复类"
    assert detail["summary"]["bucket_summary"]["already_patched"]["primary_metric"]["display_value"] == "100.00%"
    assert detail["fixtures"][0]["sample_bucket"] == "already_patched"
    assert detail["fixtures"][0]["task_detail_route"] == "/tasks/TASK-001"
