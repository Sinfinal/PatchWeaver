"""阶段评测汇总"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from patchweaver.models.attempt import AttemptRecord
from patchweaver.models.harness import ArtifactRef


class Evaluator:
    """负责输出任务级和夹具级评测摘要"""

    def summarize(self, *, attempts: list[AttemptRecord], artifacts: list[ArtifactRef]) -> dict[str, object]:
        """生成任务级评测摘要"""

        total_attempts = len(attempts)
        built_attempts = sum(1 for item in attempts if item.status == "built")
        failed_attempts = sum(1 for item in attempts if item.status == "failed")
        average_attempt_no = (sum(item.attempt_no for item in attempts) / total_attempts) if attempts else 0.0

        failure_breakdown = Counter(item.failure_type for item in attempts if item.failure_type)
        artifact_types = Counter(artifact.artifact_type for artifact in artifacts)
        latest_status = attempts[-1].status if attempts else "pending"
        latest_failure_type = attempts[-1].failure_type if attempts else None

        return {
            "total_attempts": total_attempts,
            "built_attempts": built_attempts,
            "failed_attempts": failed_attempts,
            "success_rate": round((built_attempts / total_attempts), 4) if total_attempts else 0.0,
            "average_attempt_no": round(average_attempt_no, 2),
            "latest_status": latest_status,
            "latest_failure_type": latest_failure_type,
            "failure_breakdown": dict(failure_breakdown),
            "artifact_type_counts": dict(artifact_types),
        }

    def summarize_fixture_set(
        self,
        *,
        fixture_name: str,
        fixtures: list[dict[str, Any]],
        results: list[dict[str, Any]],
    ) -> dict[str, object]:
        """汇总一组固定样例的阶段结果"""

        matched_results = {
            item["fixture_id"]: item
            for item in results
            if item.get("matched", True)
        }
        matched_items = list(matched_results.values())
        total = len(fixtures)
        matched = sum(1 for item in fixtures if item["fixture_id"] in matched_results)
        succeeded = sum(
            1
            for item in matched_items
            if item.get("final_status") in {"built", "reported", "succeeded"}
        )
        failed = sum(
            1
            for item in matched_items
            if item.get("final_status") not in {"built", "reported", "succeeded"}
        )
        average_attempts = (
            sum(float(item.get("attempts", 0)) for item in matched_items) / len(matched_items)
            if matched_items
            else 0.0
        )
        status_distribution = Counter(item.get("final_status") or "unknown" for item in matched_items)
        failure_distribution = Counter(
            item.get("latest_failure_type") or "none"
            for item in matched_items
            if item.get("latest_failure_type")
        )
        group_distribution = Counter(
            str((item.get("fixture_group") or item.get("sample_group") or item.get("group") or "default"))
            for item in results
        )

        return {
            "fixture_name": fixture_name,
            "total_fixtures": total,
            "matched_fixtures": matched,
            "missing_fixtures": total - matched,
            "success_count": succeeded,
            "failed_count": failed,
            "success_rate": round((succeeded / matched), 4) if matched else 0.0,
            "average_attempts": round(average_attempts, 2),
            "status_distribution": dict(status_distribution),
            "failure_distribution": dict(failure_distribution),
            "group_distribution": dict(group_distribution),
            "fixtures": results,
        }

    def replay_comparison(
        self,
        *,
        task_id: str,
        attempts: list[AttemptRecord],
        task_dir: Path,
    ) -> dict[str, object]:
        """整理同一任务多轮尝试的回放对比摘要"""

        attempt_items: list[dict[str, object]] = []
        for item in attempts:
            attempt_dir = task_dir / "attempts" / f"{item.attempt_no:03d}"
            attempt_items.append(
                {
                    "attempt_no": item.attempt_no,
                    "attempt_id": item.attempt_id,
                    "status": item.status,
                    "failure_type": item.failure_type,
                    "rewrite_plan_path": str(attempt_dir / "rewrite" / "rewrite_plan.json"),
                    "validation_report_path": str(attempt_dir / "artifacts" / "validation_report.json"),
                    "trace_path": str(attempt_dir / "trace" / "harness_trace.json"),
                }
            )

        return {
            "task_id": task_id,
            "attempt_count": len(attempts),
            "latest_attempt": attempts[-1].attempt_no if attempts else None,
            "items": attempt_items,
        }
