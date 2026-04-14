"""配方记忆。"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from patchweaver.models.attempt import AttemptRecord, FailureRecord
from patchweaver.models.memory import RecipeMemoryEntry
from patchweaver.models.rewrite import RewritePlan
from patchweaver.models.validation import ValidationReport
from patchweaver.memory.repository import MemoryRepository


class RecipeMemory:
    """负责配方经验的记录与召回。"""

    def __init__(self, repository: MemoryRepository) -> None:
        """绑定底层仓库。"""

        self.repository = repository

    def record(
        self,
        *,
        task_id: str,
        attempt_id: str,
        plan: RewritePlan,
        attempt: AttemptRecord,
        failure_record: FailureRecord | None = None,
        validation_report: ValidationReport | None = None,
    ) -> RecipeMemoryEntry:
        """记录一次 recipe 使用结果。"""

        entries = self.repository.load_recipe_entries()
        key = (plan.selected_recipe or "unknown", tuple(sorted(plan.rule_hits)), tuple(sorted(plan.selected_primitives)))
        matched = next(
            (
                entry
                for entry in entries
                if (
                    entry.recipe_name,
                    tuple(sorted(entry.risk_types)),
                    tuple(sorted(entry.primitives)),
                )
                == key
            ),
            None,
        )
        success = attempt.status == "built" and (
            validation_report is None or validation_report.semantic_guard_result.status != "failed"
        )
        summary = self._summary(attempt=attempt, failure_record=failure_record, validation_report=validation_report)

        if matched is None:
            matched = RecipeMemoryEntry(
                entry_id=f"RM-{uuid4().hex[:10]}",
                recipe_name=plan.selected_recipe or "unknown",
                risk_types=list(plan.rule_hits),
                primitives=list(plan.selected_primitives),
                candidate_id=plan.candidate_ids[0] if plan.candidate_ids else None,
                last_task_id=task_id,
                last_attempt_id=attempt_id,
                attempts=0,
                successes=0,
                failures=0,
            )
            entries.append(matched)

        matched.attempts += 1
        if success:
            matched.successes += 1
        else:
            matched.failures += 1
        matched.last_status = attempt.status
        matched.last_summary = summary
        matched.last_task_id = task_id
        matched.last_attempt_id = attempt_id
        matched.updated_at = datetime.now(timezone.utc)
        self.repository.save_recipe_entries(entries)
        return matched

    def recall(self, *, risk_types: list[str] | None = None, limit: int = 3) -> list[str]:
        """按风险类型召回 recipe 经验。"""

        entries = self.repository.load_recipe_entries()
        wanted = {item for item in risk_types or [] if item}
        ranked: list[RecipeMemoryEntry] = []
        for entry in entries:
            if wanted and not wanted.intersection(entry.risk_types):
                continue
            ranked.append(entry)
        ranked.sort(
            key=lambda item: (
                item.successes / item.attempts if item.attempts else 0.0,
                item.attempts,
                item.updated_at,
            ),
            reverse=True,
        )
        return [self._format(entry) for entry in ranked[:limit]]

    def snapshot(self, *, limit: int = 20) -> list[dict[str, object]]:
        """返回最近若干条配方经验快照。"""

        entries = self.repository.load_recipe_entries()
        ordered = sorted(entries, key=lambda item: item.updated_at, reverse=True)
        return [entry.model_dump(mode="json") for entry in ordered[:limit]]

    def _format(self, entry: RecipeMemoryEntry) -> str:
        """格式化单条配方经验。"""

        success_rate = entry.successes / entry.attempts if entry.attempts else 0.0
        return (
            f"[RecipeMemory] {entry.recipe_name}: 风险={','.join(entry.risk_types) or 'unknown'}，"
            f"原语={','.join(entry.primitives) or 'none'}，成功率={success_rate:.0%}"
        )

    def _summary(
        self,
        *,
        attempt: AttemptRecord,
        failure_record: FailureRecord | None,
        validation_report: ValidationReport | None,
    ) -> str:
        """整理最新结果摘要。"""

        if validation_report is not None and validation_report.semantic_guard_result.status == "failed":
            return f"验证阶段拦截：{validation_report.semantic_guard_result.detail}"
        if failure_record is not None and failure_record.failure_type not in {"", "none"}:
            return failure_record.summary
        return f"最近一次状态为 {attempt.status}。"
