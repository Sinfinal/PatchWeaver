"""联合规划骨架"""

from __future__ import annotations

from patchweaver.models.constraint import ConstraintReport
from patchweaver.models.rewrite import RewriteCandidate, RewritePlan
from patchweaver.models.semantic import SemanticCard
from patchweaver.planner.candidate_ranker import CandidateRanker
from patchweaver.planner.primitive_selector import PrimitiveSelector


class JointPlanner:
    """负责组合候选改写方案，并给出最终选择"""

    def __init__(self) -> None:
        """初始化原语选择和排序组件"""

        self.primitive_selector = PrimitiveSelector()
        self.candidate_ranker = CandidateRanker()

    def plan(
        self,
        *,
        task_id: str,
        semantic_card: SemanticCard,
        constraint_report: ConstraintReport,
        ranking_hints: dict[str, object] | None = None,
    ) -> RewritePlan:
        """根据语义卡片、约束结果和经验提示生成本轮规划"""

        primitives = self.primitive_selector.select(constraint_report)
        target_files = list(
            dict.fromkeys(
                constraint_report.target_files
                or semantic_card.touched_files
                or semantic_card.touched_functions
            )
        )
        target_functions = (
            list(dict.fromkeys(constraint_report.target_functions or semantic_card.touched_functions))
            or target_files
        )
        rule_hits = list(
            dict.fromkeys(constraint_report.dominant_risk_types or [item.risk_type for item in constraint_report.risk_items])
        )
        if not rule_hits:
            rule_hits = ["direct_apply_path"] if constraint_report.direct_apply_viable else ["constraint_review"]
        high_risk = max(1, constraint_report.high_risk_count) if constraint_report.high_risk_count > 0 else 0

        candidates = self._build_candidates(
            task_id=task_id,
            constraint_report=constraint_report,
            target_functions=target_functions,
            fallback_primitives=primitives,
            high_risk=high_risk,
        )
        ranked = self.candidate_ranker.rank(candidates, ranking_hints=ranking_hints)
        selected = ranked[0]

        selection_notes = [
            semantic_card.root_cause or "根因待后续补充",
            constraint_report.summary or "约束摘要待补充",
            f"候选数: {len(ranked)}",
            f"命中规则: {', '.join(selected.rule_hits)}",
            f"路线族: {selected.route_family}",
            f"执行模式: {selected.execution_mode}",
        ]
        if constraint_report.forbidden_actions:
            selection_notes.append("禁止动作: " + "，".join(constraint_report.forbidden_actions))
        if semantic_card.must_keep_conditions:
            selection_notes.append("关键条件: " + "；".join(semantic_card.must_keep_conditions[:2]))
        if semantic_card.critical_calls:
            selection_notes.append("关键调用: " + "，".join(semantic_card.critical_calls[:3]))
        if constraint_report.route_hints:
            selection_notes.append("路线提示: " + "；".join(item.summary for item in constraint_report.route_hints[:2]))
        if constraint_report.preferred_route:
            selection_notes.append("约束首选路线: " + constraint_report.preferred_route)
        if constraint_report.candidate_routes:
            selection_notes.append("候选路线: " + "，".join(constraint_report.candidate_routes[:4]))
        if selected.requires_kernel_scaffold and selected.scaffold_notes:
            selection_notes.append("内核辅助: " + "；".join(selected.scaffold_notes))
        if selected.ranking_reasons:
            selection_notes.append("排序依据: " + "；".join(selected.ranking_reasons))

        return RewritePlan(
            task_id=task_id,
            plan_id=f"{task_id}-plan-001",
            candidate_ids=[item.candidate_id for item in ranked],
            selected_recipe=selected.recipe_name,
            selected_route_family=selected.route_family,
            selected_execution_mode=selected.execution_mode,
            selected_primitives=selected.primitives,
            target_files=target_files,
            rule_hits=selected.rule_hits,
            requires_kernel_scaffold=selected.requires_kernel_scaffold,
            scaffold_notes=selected.scaffold_notes,
            risk_coverage=1.0 if constraint_report.risk_items else 0.0,
            selection_reason=(
                f"优先选择综合得分最高的候选，当前命中 {selected.recipe_name}，"
                f"排序得分 {selected.ranking_score:.3f}"
            ),
            notes=selection_notes,
            candidate_summaries=ranked,
        )

    def _build_candidates(
        self,
        *,
        task_id: str,
        constraint_report: ConstraintReport,
        target_functions: list[str],
        fallback_primitives: list[str],
        high_risk: int,
    ) -> list[RewriteCandidate]:
        """根据路线提示和约束结果生成候选改写路径"""

        candidates: list[RewriteCandidate] = []
        seen_keys: set[tuple[str, tuple[str, ...]]] = set()
        route_inputs: list[dict[str, object]] = []

        for hint in constraint_report.route_hints:
            route_inputs.append(
                {
                    "route_name": hint.route_name,
                    "preferred": hint.preferred,
                    "blocking_risk_types": hint.blocking_risk_types,
                    "recommended_primitives": hint.recommended_primitives,
                }
            )

        for route_name in self._derive_candidate_route_names(constraint_report):
            route_inputs.append(
                {
                    "route_name": route_name,
                    "preferred": route_name == constraint_report.preferred_route,
                    "blocking_risk_types": constraint_report.dominant_risk_types,
                    "recommended_primitives": [],
                }
            )

        for index, route_input in enumerate(route_inputs, start=1):
            route_name = str(route_input["route_name"])
            route_spec = self._resolve_route_spec(route_name)
            recommended_primitives = [
                str(item) for item in list(route_input.get("recommended_primitives") or [])
            ]
            primitives = self._merge_primitives(
                route_defaults=route_spec["default_primitives"],
                recommended_primitives=recommended_primitives,
                fallback_primitives=fallback_primitives,
            )
            key = (route_spec["recipe_name"], tuple(primitives))
            if key in seen_keys:
                continue
            seen_keys.add(key)

            blocking_risk_types = [
                str(item) for item in list(route_input.get("blocking_risk_types") or [])
            ]
            metrics = self._estimate_candidate_metrics(
                route_family=route_spec["route_family"],
                preferred=bool(route_input.get("preferred")),
                blocking_risk_count=len(blocking_risk_types),
                high_risk=high_risk,
                primitives=primitives,
                forbidden_actions=constraint_report.forbidden_actions,
                requires_kernel_scaffold=route_spec["requires_kernel_scaffold"],
            )
            candidates.append(
                RewriteCandidate(
                    candidate_id=f"{task_id}-candidate-{index:03d}",
                    recipe_name=route_spec["recipe_name"],
                    route_family=route_spec["route_family"],
                    execution_mode=route_spec["execution_mode"],
                    primitives=primitives,
                    target_functions=target_functions,
                    rule_hits=blocking_risk_types
                    or (["direct_apply_path"] if route_spec["recipe_name"] == "direct_apply_patch" else ["constraint_review"]),
                    requires_kernel_scaffold=route_spec["requires_kernel_scaffold"],
                    scaffold_notes=list(route_spec["scaffold_notes"]),
                    expected_risk=metrics["risk"],
                    expected_semantic_drift=metrics["drift"],
                    expected_build_cost=metrics["build_cost"],
                )
            )

        if candidates:
            return candidates

        route_spec = self._resolve_route_spec("minimal_livepatch_wrap")
        metrics = self._estimate_candidate_metrics(
            route_family=route_spec["route_family"],
            preferred=True,
            blocking_risk_count=len(constraint_report.dominant_risk_types),
            high_risk=high_risk,
            primitives=fallback_primitives or ["wrapper"],
            forbidden_actions=constraint_report.forbidden_actions,
            requires_kernel_scaffold=route_spec["requires_kernel_scaffold"],
        )
        return [
            RewriteCandidate(
                candidate_id=f"{task_id}-candidate-001",
                recipe_name=route_spec["recipe_name"],
                route_family=route_spec["route_family"],
                execution_mode=route_spec["execution_mode"],
                primitives=fallback_primitives or ["wrapper"],
                target_functions=target_functions,
                rule_hits=constraint_report.dominant_risk_types or ["constraint_review"],
                requires_kernel_scaffold=route_spec["requires_kernel_scaffold"],
                scaffold_notes=list(route_spec["scaffold_notes"]),
                expected_risk=metrics["risk"],
                expected_semantic_drift=metrics["drift"],
                expected_build_cost=metrics["build_cost"],
            )
        ]

    def _derive_candidate_route_names(self, constraint_report: ConstraintReport) -> list[str]:
        """把约束结果扩展成一组可竞争候选"""

        route_names: list[str] = []
        if constraint_report.preferred_route:
            route_names.append(constraint_report.preferred_route)
        route_names.extend(constraint_report.candidate_routes)

        if constraint_report.direct_apply_viable:
            route_names.append("direct_apply_patch")
        else:
            route_names.append("direct_apply_patch")
            route_names.append("minimal_livepatch_wrap")

        if constraint_report.requires_callback:
            route_names.append("callback_livepatch_wrap")
        if constraint_report.requires_shadow_variable:
            route_names.append("shadow_variable_wrap")

        if constraint_report.high_risk_count > 0 or constraint_report.dominant_risk_types:
            route_names.append("smpl_primary_rewrite")
        route_names.append("minimal_livepatch_wrap")

        ordered_names: list[str] = []
        seen: set[str] = set()
        for raw_name in route_names:
            canonical = self._resolve_route_spec(raw_name)["recipe_name"]
            if canonical in seen:
                continue
            seen.add(canonical)
            ordered_names.append(canonical)
        return ordered_names

    def _resolve_route_spec(self, route_name: str) -> dict[str, object]:
        """把路线名折叠成当前工程可执行的 recipe 定义"""

        lowered = route_name.lower()
        if lowered in {"direct_apply_patch", "direct_apply"} or "direct" in lowered:
            return {
                "recipe_name": "direct_apply_patch",
                "route_family": "direct_apply",
                "execution_mode": "direct_patch",
                "default_primitives": ["direct_apply"],
                "requires_kernel_scaffold": False,
                "scaffold_notes": [],
            }
        if lowered in {"callback_livepatch_wrap", "callback_wrap"} or "callback" in lowered:
            return {
                "recipe_name": "callback_livepatch_wrap",
                "route_family": "callback",
                "execution_mode": "callback_scaffold",
                "default_primitives": ["wrapper", "callback"],
                "requires_kernel_scaffold": True,
                "scaffold_notes": [
                    "需要补齐 callback 落点与参数透传",
                    "进入构建前需要确认辅助符号在目标内核可见",
                ],
            }
        if lowered in {"shadow_variable_wrap", "shadow_state_wrap"} or "shadow" in lowered:
            return {
                "recipe_name": "shadow_variable_wrap",
                "route_family": "shadow_variable",
                "execution_mode": "shadow_state_scaffold",
                "default_primitives": ["wrapper", "shadow_variable"],
                "requires_kernel_scaffold": True,
                "scaffold_notes": [
                    "需要补齐 shadow state 的定义与回收路径",
                    "进入构建前需要确认状态同步逻辑不会放大语义漂移",
                ],
            }
        if lowered in {"smpl_primary_rewrite", "smpl_primary"} or "smpl" in lowered:
            return {
                "recipe_name": "smpl_primary_rewrite",
                "route_family": "smpl_primary",
                "execution_mode": "smpl_primary",
                "default_primitives": ["smpl", "wrapper"],
                "requires_kernel_scaffold": False,
                "scaffold_notes": [
                    "优先通过结构化变换缩小编辑半径",
                ],
            }
        return {
            "recipe_name": "minimal_livepatch_wrap",
            "route_family": "wrapper",
            "execution_mode": "template_wrap",
            "default_primitives": ["wrapper"],
            "requires_kernel_scaffold": False,
            "scaffold_notes": [],
        }

    def _merge_primitives(
        self,
        *,
        route_defaults: list[str],
        recommended_primitives: list[str],
        fallback_primitives: list[str],
    ) -> list[str]:
        """整理当前路线最终使用的原语集合"""

        primitives = list(dict.fromkeys(recommended_primitives + route_defaults))
        if primitives:
            return primitives
        return fallback_primitives or ["wrapper"]

    def _estimate_candidate_metrics(
        self,
        *,
        route_family: str,
        preferred: bool,
        blocking_risk_count: int,
        high_risk: int,
        primitives: list[str],
        forbidden_actions: list[str],
        requires_kernel_scaffold: bool,
    ) -> dict[str, float]:
        """把路线提示折叠成候选评分输入"""

        if route_family == "direct_apply":
            base_risk = 0.08 if preferred and blocking_risk_count == 0 else 0.32 + blocking_risk_count * 0.05
            base_drift = 0.04 if preferred else 0.1
            base_build_cost = 0.08
        elif route_family == "wrapper":
            base_risk = 0.16 + max(high_risk, blocking_risk_count) * 0.07
            base_drift = 0.12 + blocking_risk_count * 0.03
            base_build_cost = 0.2
        elif route_family == "callback":
            base_risk = 0.18 + max(high_risk, blocking_risk_count) * 0.07
            base_drift = 0.14 + blocking_risk_count * 0.03
            base_build_cost = 0.24
        elif route_family == "shadow_variable":
            base_risk = 0.22 + max(high_risk, blocking_risk_count) * 0.08
            base_drift = 0.16 + blocking_risk_count * 0.03
            base_build_cost = 0.28
        else:
            base_risk = 0.2 + max(high_risk, blocking_risk_count) * 0.07
            base_drift = 0.1 + blocking_risk_count * 0.02
            base_build_cost = 0.22

        if "callback" in primitives:
            base_build_cost += 0.04
            base_drift += 0.02
        if "shadow_variable" in primitives:
            base_build_cost += 0.05
            base_drift += 0.03
        if "smpl" in primitives:
            base_build_cost += 0.03
        if forbidden_actions and route_family == "direct_apply":
            base_risk += 0.08
            base_drift += 0.04
        if requires_kernel_scaffold:
            base_build_cost += 0.05
        if not preferred:
            base_risk += 0.03

        return {
            "risk": min(0.85, round(base_risk, 2)),
            "drift": min(0.6, round(base_drift, 2)),
            "build_cost": min(0.8, round(base_build_cost, 2)),
        }
