"""失败记忆"""

from __future__ import annotations

from uuid import uuid4

from patchweaver.models.attempt import FailureRecord
from patchweaver.models.memory import FailureMemoryEntry
from patchweaver.memory.repository import MemoryRepository


class FailureMemory:
    """负责失败经验的记录与召回"""

    def __init__(self, repository: MemoryRepository) -> None:
        """绑定底层仓库"""

        self.repository = repository

    def record(
        self,
        *,
        task_id: str,
        cve_id: str,
        attempt_id: str,
        failure_record: FailureRecord,
        recipe_name: str | None = None,
        candidate_id: str | None = None,
    ) -> FailureMemoryEntry | None:
        """写入一次失败经验"""

        if failure_record.failure_type in {"none", "", None}:
            return None

        entries = self.repository.load_failure_entries()
        evidence = self._evidence_with_diagnostics(failure_record)
        entry = FailureMemoryEntry(
            entry_id=f"FM-{uuid4().hex[:10]}",
            task_id=task_id,
            cve_id=cve_id,
            attempt_id=attempt_id,
            stage_name=failure_record.stage_name,
            failure_type=failure_record.failure_type,
            summary=failure_record.summary,
            recipe_name=recipe_name,
            candidate_id=candidate_id,
            evidence=evidence,
            keywords=self._keywords(failure_record),
        )
        entries.append(entry)
        self.repository.save_failure_entries(entries)
        return entry

    def recall(
        self,
        *,
        failure_types: list[str] | None = None,
        keywords: list[str] | None = None,
        limit: int = 3,
    ) -> list[str]:
        """按失败类型或关键字召回经验摘要"""

        entries = self.repository.load_failure_entries()
        wanted_types = {item for item in failure_types or [] if item}
        wanted_keywords = {item.lower() for item in keywords or [] if item}

        ranked: list[tuple[int, FailureMemoryEntry]] = []
        for entry in entries:
            score = 0
            if wanted_types and entry.failure_type in wanted_types:
                score += 5
            if wanted_keywords:
                haystack = " ".join([entry.summary, *entry.evidence, *entry.keywords]).lower()
                score += sum(1 for keyword in wanted_keywords if keyword in haystack)
            if score <= 0 and (wanted_types or wanted_keywords):
                continue
            ranked.append((score, entry))

        ranked.sort(key=lambda item: (item[0], item[1].created_at), reverse=True)
        return [self._format(entry) for _, entry in ranked[:limit]]

    def snapshot(self, *, limit: int = 20) -> list[dict[str, object]]:
        """返回最近若干条失败经验快照"""

        entries = self.repository.load_failure_entries()
        ordered = sorted(entries, key=lambda item: item.created_at, reverse=True)
        return [entry.model_dump(mode="json") for entry in ordered[:limit]]

    def _format(self, entry: FailureMemoryEntry) -> str:
        """格式化单条经验"""

        recipe = f"，最近关联 recipe: {entry.recipe_name}" if entry.recipe_name else ""
        return f"[FailureMemory] {entry.failure_type}: {entry.summary}{recipe}"

    def _evidence_with_diagnostics(self, record: FailureRecord) -> list[str]:
        """把 Agent 下一步动作和改写分类写进失败记忆"""

        evidence = list(record.evidence)
        details = record.diagnostic_details or {}
        next_action = details.get("agent_next_action")
        if isinstance(next_action, dict) and next_action.get("action"):
            evidence.append(
                "agent_next_action="
                + str(next_action.get("action"))
                + "; retry_scope="
                + str(next_action.get("retry_scope") or "")
            )
        constraint = details.get("kpatch_constraint")
        if isinstance(constraint, dict):
            rewrite_class = constraint.get("rewrite_classification")
            if isinstance(rewrite_class, dict):
                evidence.append(
                    "rewrite_classification="
                    + str(rewrite_class.get("class") or "")
                    + "; next_strategy="
                    + str(rewrite_class.get("next_strategy") or "")
                )
        route_effectiveness = details.get("route_effectiveness")
        if isinstance(route_effectiveness, dict) and route_effectiveness.get("status"):
            evidence.append("route_effectiveness=" + str(route_effectiveness.get("status")))
        return evidence[:8]

    def _keywords(self, record: FailureRecord) -> list[str]:
        """从失败记录中提取最小关键字"""

        keywords = {record.failure_type, record.stage_name}
        lowered = " ".join(self._evidence_with_diagnostics(record)).lower()
        for token in [
            "unsupported section change",
            "fentry",
            "init section",
            "global data",
            "abi",
            "header",
            "compile",
            "apply",
            "semantic_guard_rewrite",
            "ineffective_retry",
        ]:
            if token in lowered:
                keywords.add(token.replace(" ", "_"))
        return sorted(keywords)
