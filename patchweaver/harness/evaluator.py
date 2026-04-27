"""阶段评测汇总"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from patchweaver.models.attempt import AttemptRecord
from patchweaver.models.harness import ArtifactRef

SUCCESS_STATUSES = {"built", "reported", "succeeded"}
DEFAULT_SAMPLE_BUCKET = "buildable_and_should_pass"
FIXTURE_BUCKET_ORDER = (
    "already_patched",
    "feature_not_enabled",
    "kpatch_constraint",
    "buildable_and_should_pass",
)
FIXTURE_BUCKET_META: dict[str, dict[str, str]] = {
    "already_patched": {
        "label": "目标已修复类",
        "goal": "看目标态识别是否准确",
        "primary_metric_name": "recognized_rate",
        "primary_metric_label": "目标态识别率",
    },
    "feature_not_enabled": {
        "label": "配置关闭类",
        "goal": "看配置门控识别是否准确",
        "primary_metric_name": "recognized_rate",
        "primary_metric_label": "配置关闭识别率",
    },
    "kpatch_constraint": {
        "label": "热补丁约束类",
        "goal": "看约束识别和结构化解释是否完整",
        "primary_metric_name": "explained_rate",
        "primary_metric_label": "约束解释完整率",
    },
    "buildable_and_should_pass": {
        "label": "正向可构建类",
        "goal": "看 .ko 产出率和动态验证通过率",
        "primary_metric_name": "validation_passed_rate",
        "primary_metric_label": "动态验证通过率",
    },
}
_FIXTURE_BUCKET_ALIASES = {
    "already-patched": "already_patched",
    "target_already_patched": "already_patched",
    "feature-disabled": "feature_not_enabled",
    "feature_disabled": "feature_not_enabled",
    "constraint": "kpatch_constraint",
    "kpatch-constraint": "kpatch_constraint",
    "buildable": "buildable_and_should_pass",
    "should_pass": "buildable_and_should_pass",
    "positive_pool": "buildable_and_should_pass",
}


def normalize_sample_bucket(value: Any, *, fallback: Any = None) -> str:
    """把样例桶名称收口到固定四类"""

    for candidate in (value, fallback):
        if candidate in {None, ""}:
            continue
        token = str(candidate).strip().lower().replace("-", "_")
        token = _FIXTURE_BUCKET_ALIASES.get(token, token)
        if token in FIXTURE_BUCKET_META:
            return token
    return DEFAULT_SAMPLE_BUCKET


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
        fixture_buckets = {
            str(item.get("fixture_id") or item.get("cve_id") or "unknown"): normalize_sample_bucket(
                item.get("sample_bucket"),
                fallback=item.get("fixture_group") or item.get("sample_group") or item.get("group"),
            )
            for item in fixtures
        }
        normalized_results: list[dict[str, Any]] = []
        for item in results:
            normalized = dict(item)
            normalized["sample_bucket"] = normalize_sample_bucket(
                item.get("sample_bucket"),
                fallback=fixture_buckets.get(str(item.get("fixture_id") or "")) or item.get("fixture_group"),
            )
            normalized_results.append(normalized)
        results = normalized_results
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
            if item.get("final_status") in SUCCESS_STATUSES
        )
        failed = sum(
            1
            for item in matched_items
            if item.get("final_status") not in SUCCESS_STATUSES
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
        bucket_summary: dict[str, dict[str, Any]] = {}
        bucket_order: list[str] = []
        bucket_counts: dict[str, int] = {}

        for bucket in FIXTURE_BUCKET_ORDER:
            bucket_fixture_ids = [fixture_id for fixture_id, fixture_bucket in fixture_buckets.items() if fixture_bucket == bucket]
            if not bucket_fixture_ids:
                continue

            bucket_results = [item for item in results if str(item.get("fixture_id") or "") in bucket_fixture_ids]
            bucket_matched_items = [item for item in bucket_results if item.get("matched", True)]
            bucket_total = len(bucket_fixture_ids)
            bucket_matched = len(bucket_matched_items)
            bucket_missing = bucket_total - bucket_matched
            bucket_success = sum(1 for item in bucket_matched_items if item.get("final_status") in SUCCESS_STATUSES)
            bucket_failed = sum(1 for item in bucket_matched_items if item.get("final_status") not in SUCCESS_STATUSES)
            bucket_average_attempts = (
                sum(float(item.get("attempts", 0)) for item in bucket_matched_items) / bucket_matched
                if bucket_matched
                else 0.0
            )
            bucket_status_distribution = Counter(item.get("final_status") or "unknown" for item in bucket_matched_items)
            bucket_failure_distribution = Counter(
                item.get("latest_failure_type") or "none"
                for item in bucket_matched_items
                if item.get("latest_failure_type")
            )

            primary_metric = {
                "name": FIXTURE_BUCKET_META[bucket]["primary_metric_name"],
                "label": FIXTURE_BUCKET_META[bucket]["primary_metric_label"],
                "value": 0.0,
                "display_value": "0.00%",
                "numerator": 0,
                "denominator": bucket_matched,
            }
            secondary_metric: dict[str, Any] | None = None
            recognized_count = 0
            explained_count = 0
            built_count = 0
            validation_passed_count = 0

            if bucket == "already_patched":
                recognized_count = sum(
                    1
                    for item in bucket_matched_items
                    if item.get("latest_target_state") == "target_already_patched"
                    or item.get("latest_failure_type") == "target_already_patched"
                )
                recognized_rate = round((recognized_count / bucket_matched), 4) if bucket_matched else 0.0
                primary_metric.update(
                    {
                        "value": recognized_rate,
                        "display_value": f"{recognized_rate:.2%}",
                        "numerator": recognized_count,
                    }
                )
            elif bucket == "feature_not_enabled":
                recognized_count = sum(
                    1
                    for item in bucket_matched_items
                    if item.get("latest_failure_type") == "feature_not_enabled"
                )
                recognized_rate = round((recognized_count / bucket_matched), 4) if bucket_matched else 0.0
                primary_metric.update(
                    {
                        "value": recognized_rate,
                        "display_value": f"{recognized_rate:.2%}",
                        "numerator": recognized_count,
                    }
                )
            elif bucket == "kpatch_constraint":
                recognized_count = sum(
                    1
                    for item in bucket_matched_items
                    if item.get("latest_failure_type") == "kpatch_constraint"
                )
                explained_count = sum(
                    1
                    for item in bucket_matched_items
                    if item.get("latest_failure_type") == "kpatch_constraint"
                    and item.get("constraint_report_ready")
                )
                explained_rate = round((explained_count / bucket_matched), 4) if bucket_matched else 0.0
                recognized_rate = round((recognized_count / bucket_matched), 4) if bucket_matched else 0.0
                primary_metric.update(
                    {
                        "value": explained_rate,
                        "display_value": f"{explained_rate:.2%}",
                        "numerator": explained_count,
                    }
                )
                secondary_metric = {
                    "name": "recognized_rate",
                    "label": "约束识别率",
                    "value": recognized_rate,
                    "display_value": f"{recognized_rate:.2%}",
                    "numerator": recognized_count,
                    "denominator": bucket_matched,
                }
            else:
                built_count = sum(1 for item in bucket_matched_items if item.get("module_built"))
                validation_passed_count = sum(
                    1
                    for item in bucket_matched_items
                    if item.get("validation_status") == "passed"
                )
                built_rate = round((built_count / bucket_matched), 4) if bucket_matched else 0.0
                validation_passed_rate = round((validation_passed_count / bucket_matched), 4) if bucket_matched else 0.0
                primary_metric.update(
                    {
                        "value": validation_passed_rate,
                        "display_value": f"{validation_passed_rate:.2%}",
                        "numerator": validation_passed_count,
                    }
                )
                secondary_metric = {
                    "name": "module_built_rate",
                    "label": ".ko 产出率",
                    "value": built_rate,
                    "display_value": f"{built_rate:.2%}",
                    "numerator": built_count,
                    "denominator": bucket_matched,
                }

            bucket_summary[bucket] = {
                "bucket": bucket,
                "label": FIXTURE_BUCKET_META[bucket]["label"],
                "goal": FIXTURE_BUCKET_META[bucket]["goal"],
                "total_fixtures": bucket_total,
                "matched_fixtures": bucket_matched,
                "missing_fixtures": bucket_missing,
                "success_count": bucket_success,
                "failed_count": bucket_failed,
                "success_rate": round((bucket_success / bucket_matched), 4) if bucket_matched else 0.0,
                "average_attempts": round(bucket_average_attempts, 2),
                "status_distribution": dict(bucket_status_distribution),
                "failure_distribution": dict(bucket_failure_distribution),
                "recognized_count": recognized_count,
                "explained_count": explained_count,
                "module_built_count": built_count,
                "validation_passed_count": validation_passed_count,
                "primary_metric": primary_metric,
                "secondary_metric": secondary_metric,
                "fixture_ids": bucket_fixture_ids,
            }
            bucket_order.append(bucket)
            bucket_counts[bucket] = bucket_total

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
            "bucket_order": bucket_order,
            "bucket_counts": bucket_counts,
            "bucket_summary": bucket_summary,
            "mixed_summary_note": "兼容总成功率只用于存量接口兼容，不再作为固定样例的主结论",
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
