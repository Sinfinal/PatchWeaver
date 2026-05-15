"""双记忆门面"""

from __future__ import annotations

import json
import re
from pathlib import Path

from patchweaver.agent.planning_contracts import ReflectionRecord
from patchweaver.models.attempt import AttemptRecord, FailureRecord
from patchweaver.models.evidence import EvidenceBundle
from patchweaver.models.memory import FailureMemoryEntry, RecipeMemoryEntry
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
        "no_fentry_target",
        "init_code_change",
        "static_local_change",
        "global_data_change",
        "struct_layout_change",
        "header_abi_change",
        "unsupported_section_change",
        "inline_side_effect",
        "unknown_patchability",
        "kpatch_constraint",
        "kpatch_constraint_unresolved",
        "unfixable_by_livepatch",
        # 兼容旧口径，避免已有记忆和历史样例失联
        "missing_fentry",
        "init_section",
        "direct_apply_ready",
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

    def record_reflection(
        self,
        reflection: ReflectionRecord,
        *,
        task: TaskContext | None = None,
        failure_record: FailureRecord | None = None,
        recipe_name: str | None = None,
        candidate_id: str | None = None,
    ) -> dict[str, object]:
        """Mirror Agent reflections into failure and recipe memory."""

        failure_entries = self.repository.load_failure_entries()
        reflection_id = self._reflection_id(reflection)
        attempt_id = failure_record.attempt_id if failure_record is not None else reflection_id
        task_id = task.task_id if task is not None else "unknown"
        cve_id = task.cve_id if task is not None else "unknown"
        if not any(entry.entry_id == f"FM-{reflection_id}" for entry in failure_entries):
            failure_entries.append(
                FailureMemoryEntry(
                    entry_id=f"FM-{reflection_id}",
                    task_id=task_id,
                    cve_id=cve_id,
                    attempt_id=attempt_id,
                    stage_name=failure_record.stage_name if failure_record is not None else "agent_reflection",
                    failure_type=reflection.failure_type,
                    summary=reflection.what_failed,
                    recipe_name=recipe_name or self._first_disabled_strategy(reflection),
                    candidate_id=candidate_id,
                    evidence=[
                        reflection.what_to_avoid,
                        reflection.next_strategy_hint,
                        *reflection.evidence_refs,
                    ][:8],
                    keywords=self._reflection_keywords(reflection),
                )
            )
            self.repository.save_failure_entries(failure_entries)

        recipe = recipe_name or self._first_disabled_strategy(reflection)
        if recipe:
            recipe_entries = self.repository.load_recipe_entries()
            entry_id = f"RM-{reflection_id}-{recipe}"
            matched = next((entry for entry in recipe_entries if entry.entry_id == entry_id), None)
            if matched is None:
                matched = RecipeMemoryEntry(
                    entry_id=entry_id,
                    recipe_name=recipe,
                    risk_types=[reflection.failure_type],
                    primitives=[],
                    candidate_id=candidate_id,
                    last_task_id=task_id,
                    last_attempt_id=attempt_id,
                )
                recipe_entries.append(matched)
            matched.attempts = max(1, matched.attempts)
            matched.failures = max(1, matched.failures)
            matched.last_status = "reflection_failed"
            matched.last_summary = reflection.what_failed
            matched.last_task_id = task_id
            matched.last_attempt_id = attempt_id
            self.repository.save_recipe_entries(recipe_entries)

        self._save_reflection_memory(reflection, cve_id=cve_id)
        return self.repository.snapshot()

    def load_reflections(self, *, limit: int = 8, cve_id: str | None = None) -> list[ReflectionRecord]:
        """Load memory-backed Agent reflections, optionally filtered by CVE."""

        path = self.repository.root_dir / "reflection_memory.json"
        if not path.exists():
            return []
        try:
            raw = json.loads(path.read_text(encoding="utf-8") or "[]")
        except (OSError, ValueError):
            return []
        if not isinstance(raw, list):
            return []
        reflections: list[ReflectionRecord] = []
        for item in raw:
            try:
                r = ReflectionRecord.model_validate(item)
                # 只加载同一 CVE 的 reflection，避免跨任务污染
                if cve_id and item.get("cve_id") and item.get("cve_id") != cve_id:
                    continue
                reflections.append(r)
            except ValueError:
                continue
        return reflections[-limit:]

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

    def build_ranking_hints(self, *, risk_types: list[str], task_id: str | None = None) -> dict[str, object]:
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
        avoid_recipes: dict[str, str] = {}
        boost_recipes: dict[str, str] = {}
        extra_candidate_routes: list[str] = []
        for entry in failure_entries:
            is_task_entry = task_id is not None and entry.task_id == task_id
            if normalized_risks and entry.failure_type not in normalized_risks and not is_task_entry:
                continue
            failure_pressure[entry.failure_type] = failure_pressure.get(entry.failure_type, 0) + 1
            recent_failures.setdefault(entry.failure_type, entry.summary)
            if is_task_entry and entry.recipe_name:
                avoid_recipes.setdefault(entry.recipe_name, entry.summary)
                retry_routes = self._retry_routes_for_failure(entry.failure_type, entry.summary, entry.evidence)
                for route_name, reason in retry_routes.items():
                    boost_recipes.setdefault(route_name, reason)
                    if route_name not in extra_candidate_routes:
                        extra_candidate_routes.append(route_name)

        return {
            "risk_types": normalized_risks,
            "recipe_stats": recipe_stats,
            "failure_pressure": failure_pressure,
            "recent_failures": recent_failures,
            "avoid_recipes": avoid_recipes,
            "boost_recipes": boost_recipes,
            "extra_candidate_routes": extra_candidate_routes,
        }

    def _retry_routes_for_failure(
        self,
        failure_type: str,
        summary: str,
        evidence: list[str],
    ) -> dict[str, str]:
        """把失败归因转成下一轮规划可用的替代路线"""

        if failure_type != "kpatch_constraint":
            return {}

        combined = " ".join([summary, *evidence]).lower()
        if "semantic_guard_rewrite" in combined or "rewritable_by_semantic_guard" in combined:
            return {
                "semantic_guard_rewrite": "失败归因判断该样例可做函数局部 guard 收缩，优先执行 semantic guard 改写",
                "section_change_avoidance_rewrite": "若 guard 收缩仍命中后端约束，再移除全局和初始化类高风险 hunk",
                "smpl_primary_rewrite": "保留结构化收缩路线作为对照",
            }
        if "unsupported section change" in combined or "section mismatch" in combined:
            return {
                "section_change_avoidance_rewrite": "上一轮命中 section 变化约束，优先移除全局和初始化类高风险 hunk",
                "smpl_primary_rewrite": "上一轮命中 section 变化约束，优先缩小结构化编辑半径",
                "state_preserving_wrap": "上一轮命中 section 变化约束，保留状态迁移路线作为候选",
                "shadow_variable_wrap": "上一轮命中 section 变化约束，保留 shadow state 路线作为候选",
            }
        if "fentry" in combined:
            return {
                "callback_livepatch_wrap": "上一轮命中 fentry 约束，优先尝试 callback 路线",
                "smpl_primary_rewrite": "上一轮命中 fentry 约束，保留结构化收缩路线",
            }
        if "unreconcilable difference" in combined or "global data" in combined:
            return {
                "shadow_variable_wrap": "上一轮命中全局状态差异，优先尝试 shadow state 路线",
                "state_preserving_wrap": "上一轮命中状态差异，保留状态迁移路线",
            }
        return {
            "smpl_primary_rewrite": "上一轮命中 kpatch 约束，优先尝试结构化改写",
            "minimal_livepatch_wrap": "上一轮命中 kpatch 约束，保留最小 wrapper 对照路线",
        }

    def _save_reflection_memory(self, reflection: ReflectionRecord, cve_id: str | None = None) -> None:
        """Persist a compact reflection ledger beside existing memory files."""

        path = self.repository.root_dir / "reflection_memory.json"
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8") or "[]")
            except (OSError, ValueError):
                raw = []
        else:
            raw = []
        if not isinstance(raw, list):
            raw = []
        reflection_id = self._reflection_id(reflection)
        entries = [item for item in raw if not isinstance(item, dict) or item.get("reflection_id") != reflection_id]
        entry = reflection.model_dump(mode="json")
        if cve_id:
            entry["cve_id"] = cve_id
        entries.append(entry)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _reflection_id(self, reflection: ReflectionRecord) -> str:
        return reflection.reflection_id or f"reflection-{reflection.attempt_no or 'unknown'}-{reflection.failure_type}"

    def _first_disabled_strategy(self, reflection: ReflectionRecord) -> str | None:
        return reflection.disabled_strategies[0] if reflection.disabled_strategies else None

    def _reflection_keywords(self, reflection: ReflectionRecord) -> list[str]:
        keywords = {reflection.failure_type, "agent_reflection"}
        keywords.update(reflection.disabled_strategies)
        combined = " ".join([reflection.what_failed, reflection.what_to_avoid, reflection.next_strategy_hint]).lower()
        for token in [
            "stable_source_baseline",
            "reverse_unpatch",
            "context_adapter",
            "semantic_guard_rewrite",
            "section_change_avoidance",
            "ineffective_retry",
            "terminal",
        ]:
            if token in combined:
                keywords.add(token)
        return sorted(keywords)

    def _keywords(self, evidence_bundle: EvidenceBundle) -> list[str]:
        """从证据中提取最小关键字集合"""

        combined = " ".join([span.excerpt for span in evidence_bundle.spans] + evidence_bundle.memory_hits).lower()
        tokens = set(re.findall(r"[a-z_][a-z0-9_:-]{2,}", combined))
        for span in evidence_bundle.spans:
            stem = Path(span.source_path).stem.lower()
            if stem:
                tokens.add(stem)
        return sorted(tokens)
