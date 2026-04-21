"""双记忆门面"""

from __future__ import annotations

import re
from pathlib import Path

from patchweaver.models.attempt import AttemptRecord, FailureRecord
from patchweaver.models.evidence import EvidenceBundle
from patchweaver.models.rewrite import RewritePlan
from patchweaver.models.task import TaskContext
from patchweaver.models.validation import ValidationReport
from patchweaver.memory.failure_memory import FailureMemory
from patchweaver.memory.recipe_memory import RecipeMemory
from patchweaver.memory.repository import MemoryRepository


class DualMemory:
    """统一管理 Failure Memory 与 Recipe Memory"""

    KNOWN_RISK_TYPES = {
        "patch_apply_failed",
        "missing_fentry",
        "init_section",
        "global_data_change",
        "header_abi_change",
        "unknown_patchability",
        "direct_apply_ready",
        "kpatch_constraint",
    }

    def __init__(self, root_dir: Path) -> None:
        """初始化双记忆仓库"""

        repository = MemoryRepository(root_dir)
        self.failure_memory = FailureMemory(repository)
        self.recipe_memory = RecipeMemory(repository)
        self.repository = repository

    def record_attempt(
        self,
        *,
        task: TaskContext,
        plan: RewritePlan,
        attempt: AttemptRecord,
        failure_record: FailureRecord,
        validation_report: ValidationReport | None = None,
    ) -> dict[str, object]:
        """记录单轮执行结果并返回双记忆快照"""

        self.failure_memory.record(
            task_id=task.task_id,
            cve_id=task.cve_id,
            attempt_id=attempt.attempt_id,
            failure_record=failure_record,
            recipe_name=plan.selected_recipe,
            candidate_id=attempt.candidate_id,
        )
        self.recipe_memory.record(
            task_id=task.task_id,
            attempt_id=attempt.attempt_id,
            plan=plan,
            attempt=attempt,
            failure_record=failure_record,
            validation_report=validation_report,
        )
        return {
            "failure_memory": self.failure_memory.snapshot(),
            "recipe_memory": self.recipe_memory.snapshot(),
        }

    def recall(self, *, stage_name: str, evidence_bundle: EvidenceBundle, limit: int = 3) -> list[str]:
        """按阶段召回经验摘要"""

        keywords = self._keywords(evidence_bundle)
        risk_types = [item for item in keywords if item in self.KNOWN_RISK_TYPES]
        if stage_name == "failure_analysis":
            return self.failure_memory.recall(failure_types=risk_types, keywords=keywords, limit=limit)
        if stage_name in {"rewrite_recipe", "validation"}:
            recipe_hits = self.recipe_memory.recall(risk_types=risk_types, limit=limit)
            failure_hits = self.failure_memory.recall(keywords=keywords, limit=max(1, limit - len(recipe_hits)))
            return (recipe_hits + failure_hits)[:limit]
        if stage_name == "reporting":
            recipe_hits = self.recipe_memory.recall(risk_types=risk_types, limit=limit)
            if recipe_hits:
                return recipe_hits
            return self.failure_memory.recall(keywords=keywords, limit=limit)
        return []

    def build_ranking_hints(self, *, risk_types: list[str]) -> dict[str, object]:
        """为候选排序整理一份轻量经验提示"""

        normalized_risks = [item for item in dict.fromkeys(risk_types) if item]
        recipe_entries = self.repository.load_recipe_entries()
        failure_entries = self.repository.load_failure_entries()

        recipe_stats: dict[str, dict[str, object]] = {}
        for entry in recipe_entries:
            if normalized_risks and not set(entry.risk_types).intersection(normalized_risks):
                continue
            success_rate = entry.successes / entry.attempts if entry.attempts else 0.0
            failure_rate = entry.failures / entry.attempts if entry.attempts else 0.0
            current = recipe_stats.get(entry.recipe_name)
            candidate_payload = {
                "attempts": entry.attempts,
                "success_rate": round(success_rate, 4),
                "failure_rate": round(failure_rate, 4),
                "last_status": entry.last_status,
                "last_summary": entry.last_summary,
                "risk_types": list(entry.risk_types),
            }
            if current is None or candidate_payload["attempts"] >= int(current["attempts"]):
                recipe_stats[entry.recipe_name] = candidate_payload

        failure_pressure: dict[str, int] = {}
        recent_failures: dict[str, str] = {}
        for entry in failure_entries:
            if normalized_risks and entry.failure_type not in normalized_risks:
                continue
            failure_pressure[entry.failure_type] = failure_pressure.get(entry.failure_type, 0) + 1
            recent_failures.setdefault(entry.failure_type, entry.summary)

        return {
            "risk_types": normalized_risks,
            "recipe_stats": recipe_stats,
            "failure_pressure": failure_pressure,
            "recent_failures": recent_failures,
        }

    def _keywords(self, evidence_bundle: EvidenceBundle) -> list[str]:
        """从证据中提取最小关键字集合"""

        combined = " ".join([span.excerpt for span in evidence_bundle.spans] + evidence_bundle.memory_hits).lower()
        tokens = set(re.findall(r"[a-z_][a-z0-9_:-]{2,}", combined))
        for span in evidence_bundle.spans:
            stem = Path(span.source_path).stem.lower()
            if stem:
                tokens.add(stem)
        return sorted(tokens)
