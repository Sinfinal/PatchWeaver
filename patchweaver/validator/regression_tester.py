"""回归测试器"""

from __future__ import annotations

from collections import Counter

from patchweaver.models.attempt import AttemptRecord
from patchweaver.models.validation import ValidationItem


class RegressionTester:
    """负责根据历史尝试整理一份轻量回归结论"""

    def run(
        self,
        *,
        current_attempt: AttemptRecord,
        history_attempts: list[AttemptRecord],
        semantic_guard_passed: bool,
    ) -> tuple[ValidationItem, dict[str, object], str]:
        """比较当前轮与历史记录，输出回归摘要"""

        if not history_attempts:
            item = ValidationItem(status="skipped", ok=False, detail="当前没有历史尝试，暂不生成回归对比。")
            summary = {
                "history_attempts": 0,
                "history_failure_types": {},
                "improved": False,
                "baseline": "missing",
            }
            return item, summary, self._build_log(item, summary)

        history_failures = Counter(item.failure_type or "none" for item in history_attempts)
        previously_built = any(item.status == "built" for item in history_attempts)
        improved = current_attempt.status == "built" and not previously_built
        same_failure = bool(current_attempt.failure_type and history_failures.get(current_attempt.failure_type, 0))

        if current_attempt.status == "built" and semantic_guard_passed:
            detail = "当前结果相比历史记录已达到可接受基线。"
            if improved:
                detail = "当前结果首次构建成功，较历史记录有明显改善。"
            item = ValidationItem(status="passed", ok=True, detail=detail)
        elif same_failure:
            item = ValidationItem(status="failed", ok=False, detail="当前轮重复落入历史高频失败类型。")
        else:
            item = ValidationItem(status="skipped", ok=False, detail="当前轮与历史相比出现了新结果，但尚未形成稳定回归结论。")

        summary = {
            "history_attempts": len(history_attempts),
            "history_failure_types": dict(history_failures),
            "improved": improved,
            "baseline": "available",
            "current_status": current_attempt.status,
            "current_failure_type": current_attempt.failure_type,
        }
        return item, summary, self._build_log(item, summary)

    def _build_log(self, item: ValidationItem, summary: dict[str, object]) -> str:
        """整理回归说明日志"""

        lines = [
            f"status: {item.status}",
            f"detail: {item.detail}",
            f"history_attempts: {summary.get('history_attempts', 0)}",
            f"improved: {summary.get('improved', False)}",
        ]
        failure_types = summary.get("history_failure_types") or {}
        if failure_types:
            lines.append("history_failure_types:")
            for name, count in sorted(failure_types.items()):
                lines.append(f"  - {name}: {count}")
        return "\n".join(lines) + "\n"
