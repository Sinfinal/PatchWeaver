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

    def _keywords(self, evidence_bundle: EvidenceBundle) -> list[str]:
        """从证据中提取最小关键字集合"""

        combined = " ".join([span.excerpt for span in evidence_bundle.spans] + evidence_bundle.memory_hits).lower()
        tokens = set(re.findall(r"[a-z_][a-z0-9_:-]{2,}", combined))
        for span in evidence_bundle.spans:
            stem = Path(span.source_path).stem.lower()
            if stem:
                tokens.add(stem)
        return sorted(tokens)
