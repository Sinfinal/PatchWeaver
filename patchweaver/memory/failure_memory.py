"""失败记忆。"""

from __future__ import annotations

from uuid import uuid4

from patchweaver.models.attempt import FailureRecord
from patchweaver.models.memory import FailureMemoryEntry
from patchweaver.memory.repository import MemoryRepository


class FailureMemory:
    """负责失败经验的记录与召回。"""

    def __init__(self, repository: MemoryRepository) -> None:
        """绑定底层仓库。"""

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
        """写入一次失败经验。"""

        if failure_record.failure_type in {"none", "", None}:
            return None

        entries = self.repository.load_failure_entries()
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
            evidence=list(failure_record.evidence),
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
        """按失败类型或关键字召回经验摘要。"""

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
        """返回最近若干条失败经验快照。"""

        entries = self.repository.load_failure_entries()
        ordered = sorted(entries, key=lambda item: item.created_at, reverse=True)
        return [entry.model_dump(mode="json") for entry in ordered[:limit]]

    def _format(self, entry: FailureMemoryEntry) -> str:
        """格式化单条经验。"""

        recipe = f"，最近关联 recipe: {entry.recipe_name}" if entry.recipe_name else ""
        return f"[FailureMemory] {entry.failure_type}: {entry.summary}{recipe}"

    def _keywords(self, record: FailureRecord) -> list[str]:
        """从失败记录中提取最小关键字。"""

        keywords = {record.failure_type, record.stage_name}
        lowered = " ".join(record.evidence).lower()
        for token in ["fentry", "init section", "global data", "abi", "header", "compile", "apply"]:
            if token in lowered:
                keywords.add(token.replace(" ", "_"))
        return sorted(keywords)
