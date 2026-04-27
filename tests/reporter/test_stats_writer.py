from __future__ import annotations

from pathlib import Path

from patchweaver.reporter.stats_writer import StatsWriter


def test_stats_writer_renders_bucket_summary(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir(parents=True, exist_ok=True)
    target_path = project_root / "data" / "evaluations" / "contest_samples" / "summary.md"

    payload = {
        "fixture_name": "contest_samples",
        "total_fixtures": 2,
        "matched_fixtures": 2,
        "missing_fixtures": 0,
        "success_count": 1,
        "failed_count": 1,
        "success_rate": 0.5,
        "average_attempts": 1.5,
        "mixed_summary_note": "兼容总成功率只用于存量接口兼容",
        "bucket_order": ["already_patched", "buildable_and_should_pass"],
        "bucket_summary": {
            "already_patched": {
                "label": "目标已修复类",
                "goal": "看目标态识别是否准确",
                "total_fixtures": 1,
                "matched_fixtures": 1,
                "missing_fixtures": 0,
                "status_distribution": {"target_state": 1},
                "failure_distribution": {"target_already_patched": 1},
                "primary_metric": {
                    "label": "目标态识别率",
                    "display_value": "100.00%",
                    "numerator": 1,
                    "denominator": 1,
                },
                "secondary_metric": None,
            },
            "buildable_and_should_pass": {
                "label": "正向可构建类",
                "goal": "看 .ko 产出率和动态验证通过率",
                "total_fixtures": 1,
                "matched_fixtures": 1,
                "missing_fixtures": 0,
                "status_distribution": {"built": 1},
                "failure_distribution": {},
                "primary_metric": {
                    "label": "动态验证通过率",
                    "display_value": "100.00%",
                    "numerator": 1,
                    "denominator": 1,
                },
                "secondary_metric": {
                    "label": ".ko 产出率",
                    "display_value": "100.00%",
                    "numerator": 1,
                    "denominator": 1,
                },
            },
        },
        "status_distribution": {"target_state": 1, "built": 1},
        "group_distribution": {"challenge_dev": 2},
        "failure_distribution": {"target_already_patched": 1},
        "fixtures": [
            {
                "fixture_id": "fixture-1",
                "sample_bucket": "already_patched",
                "final_status": "target_state",
                "attempts": 1,
                "latest_failure_type": "target_already_patched",
            }
        ],
    }

    StatsWriter(project_root).write_markdown(payload, target_path)
    content = target_path.read_text(encoding="utf-8")

    assert "## 分桶评测" in content
    assert "### 目标已修复类" in content
    assert "主指标: 目标态识别率 100.00% (1/1)" in content
    assert "### 正向可构建类" in content
    assert "次指标: .ko 产出率 100.00% (1/1)" in content
