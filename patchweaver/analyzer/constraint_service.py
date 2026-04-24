"""约束诊断骨架"""

from __future__ import annotations

from patchweaver.models.constraint import ConstraintReport, RiskItem, RouteHint
from patchweaver.models.patch import PatchBundle
from patchweaver.models.semantic import SemanticCard
from patchweaver.analyzer.risk_rule_registry import RiskRuleRegistry


class ConstraintDiagnoser:
    """负责生成热补丁约束报告"""

    def __init__(self) -> None:
        """初始化风险规则注册表"""

        self.registry = RiskRuleRegistry()

    def diagnose(
        self,
        patch_bundle: PatchBundle,
        semantic_card: SemanticCard | None = None,
        *,
        semantic_card_source: str = "unavailable",
        semantic_card_enriched: bool = False,
    ) -> ConstraintReport:
        """根据补丁内容返回最小约束报告"""

        risk_items = self.registry.evaluate(patch_bundle, semantic_card=semantic_card)
        direct_apply_viable = self.registry.direct_apply_ready(patch_bundle)
        target_files = list(dict.fromkeys((semantic_card.touched_files if semantic_card is not None else []) or patch_bundle.affected_files))
        target_functions = list(dict.fromkeys(semantic_card.touched_functions if semantic_card is not None else []))
        suggested_primitives = self._suggested_primitives(risk_items=risk_items, direct_apply_viable=direct_apply_viable)
        forbidden_actions = self._forbidden_actions(risk_items)
        route_hints = self._route_hints(
            risk_items=risk_items,
            direct_apply_viable=direct_apply_viable,
            suggested_primitives=suggested_primitives,
            target_functions=target_functions,
        )
        candidate_routes, preferred_route = self._candidate_routes(
            risk_items=risk_items,
            direct_apply_viable=direct_apply_viable,
            suggested_primitives=suggested_primitives,
        )
        return ConstraintReport(
            task_id=patch_bundle.task_id,
            semantic_card_source=semantic_card_source if semantic_card is not None else "unavailable",
            semantic_card_enriched=semantic_card_enriched if semantic_card is not None else False,
            target_files=target_files,
            target_functions=target_functions,
            risk_items=risk_items,
            dominant_risk_types=[item.risk_type for item in risk_items],
            suggested_primitives=suggested_primitives,
            forbidden_actions=forbidden_actions,
            route_hints=route_hints,
            candidate_routes=candidate_routes,
            preferred_route=preferred_route,
            high_risk_count=sum(1 for item in risk_items if item.severity == "high"),
            requires_callback=any("callback" in item.required_primitives for item in risk_items),
            requires_shadow_variable=any("shadow_variable" in item.required_primitives for item in risk_items),
            direct_apply_viable=direct_apply_viable,
            summary=self._build_summary(
                risk_items,
                semantic_card=semantic_card,
                direct_apply_viable=direct_apply_viable,
                suggested_primitives=suggested_primitives,
            ),
        )

    def _build_summary(
        self,
        risk_items: list[RiskItem],
        *,
        semantic_card: SemanticCard | None,
        direct_apply_viable: bool,
        suggested_primitives: list[str],
    ) -> str:
        """把风险项压成一条适合状态页和报告复用的摘要"""

        if not risk_items:
            if direct_apply_viable:
                return "当前未命中显式热补丁约束，补丁形态满足 direct apply 预检查，可直接进入改写与构建前预检查"
            return "当前没有命中显式约束规则，但补丁形态也未稳定满足 direct apply 预检查，需继续结合 apply 预检查和构建结果判断"

        risk_types = [getattr(item, "risk_type", "") for item in risk_items if getattr(item, "risk_type", "")]
        touched_functions = semantic_card.touched_functions if semantic_card is not None else []
        function_hint = f"涉及函数 {', '.join(touched_functions[:2])}" if touched_functions else "当前未稳定抽到函数级范围"
        primitive_hint = f"建议原语 {', '.join(suggested_primitives)}" if suggested_primitives else "当前未生成明确原语建议"
        if risk_types == ["unknown_patchability"]:
            return f"当前规则库未命中明确约束类型，{function_hint}，{primitive_hint}"
        return f"命中 {len(risk_types)} 类热补丁约束：{', '.join(risk_types)}，{function_hint}，{primitive_hint}"

    def _suggested_primitives(self, *, risk_items: list[RiskItem], direct_apply_viable: bool) -> list[str]:
        """从风险项和补丁形态整理建议原语集合"""

        primitives: list[str] = []
        if direct_apply_viable:
            primitives.append("direct_apply")
        for item in risk_items:
            primitives.extend(item.required_primitives)
        return sorted(dict.fromkeys(primitives))

    def _forbidden_actions(self, risk_items: list[RiskItem]) -> list[str]:
        """汇总所有风险项给出的禁止动作"""

        actions: list[str] = []
        for item in risk_items:
            actions.extend(item.forbidden_actions)
        return sorted(dict.fromkeys(actions))

    def _route_hints(
        self,
        *,
        risk_items: list[RiskItem],
        direct_apply_viable: bool,
        suggested_primitives: list[str],
        target_functions: list[str],
    ) -> list[RouteHint]:
        """根据当前风险项生成改写路线提示"""

        risk_types = [item.risk_type for item in risk_items]
        route_hints: list[RouteHint] = []
        function_hint = f"涉及函数 {', '.join(target_functions[:2])}" if target_functions else "当前按文件级范围继续推进"
        candidate_routes, preferred_route = self._candidate_routes(
            risk_items=risk_items,
            direct_apply_viable=direct_apply_viable,
            suggested_primitives=suggested_primitives,
        )
        preferred_hint = preferred_route or "minimal_livepatch_wrap"

        if not risk_items and direct_apply_viable:
            route_hints.append(
                RouteHint(
                    route_name="direct_apply_patch",
                    summary=f"当前未命中显式热补丁约束，{function_hint}，优先走 direct_apply 路线",
                    recommended_primitives=["direct_apply"],
                    blocking_risk_types=[],
                    preferred=True,
                )
            )
            return route_hints

        if risk_items:
            preferred_primitives = self._preferred_route_primitives(
                preferred_route=preferred_hint,
                suggested_primitives=suggested_primitives,
            )
            route_hints.append(
                RouteHint(
                    route_name=preferred_hint,
                    summary=(
                        f"当前已命中约束 {', '.join(risk_types)}，{function_hint}，"
                        f"首选语义路线 {preferred_hint}，后续规划层应优先按该路线组织候选"
                    ),
                    recommended_primitives=preferred_primitives,
                    blocking_risk_types=risk_types,
                    preferred=True,
                )
            )
            if direct_apply_viable:
                route_hints.append(
                    RouteHint(
                        route_name="direct_apply_patch",
                        summary=(
                            "补丁形态仍满足 direct apply 预检查，可保留为对照路径，"
                            f"当前候选路线集合为 {', '.join(candidate_routes)}，但不作为当前首选"
                        ),
                        recommended_primitives=["direct_apply"],
                        blocking_risk_types=risk_types,
                        preferred=False,
                    )
                )
            return route_hints

        route_hints.append(
            RouteHint(
                route_name="minimal_livepatch_wrap",
                summary=(
                    f"当前未命中显式规则，但缺少 direct apply 形态保证，{function_hint}，"
                    f"默认首选 {preferred_hint}，执行层先走 minimal_livepatch_wrap recipe"
                ),
                recommended_primitives=["wrapper"],
                blocking_risk_types=["unknown_patchability"],
                preferred=True,
            )
        )
        return route_hints

    def _preferred_route_primitives(self, *, preferred_route: str, suggested_primitives: list[str]) -> list[str]:
        """按首选路线补齐更贴近当前语义的原语集合"""

        primitives = [item for item in suggested_primitives if item != "direct_apply"]
        if preferred_route != "direct_apply_patch" and "wrapper" not in primitives:
            primitives.insert(0, "wrapper")
        if "callback" in preferred_route and "callback" not in primitives:
            primitives.append("callback")
        if "shadow" in preferred_route and "shadow_variable" not in primitives:
            primitives.append("shadow_variable")
        if "state_preserving" in preferred_route and "state_preserving" not in primitives:
            primitives.append("state_preserving")
        return list(dict.fromkeys(primitives)) or ["wrapper"]

    def _candidate_routes(
        self,
        *,
        risk_items: list[RiskItem],
        direct_apply_viable: bool,
        suggested_primitives: list[str],
    ) -> tuple[list[str], str | None]:
        """给规划层输出更细的候选路线语义，不把执行 recipe 和语义路线混成一层"""

        if not risk_items and direct_apply_viable:
            return ["direct_apply_patch"], "direct_apply_patch"

        risk_types = {item.risk_type for item in risk_items}
        primitives = set(suggested_primitives)
        routes: list[str] = []
        state_shadow_risks = {
            "global_data_change",
            "static_local_change",
        }
        state_preserving_risks = {
            "struct_layout_change",
            "header_abi_change",
        }
        shadow_required = "shadow_variable" in primitives or bool(risk_types & state_shadow_risks)
        callback_required = "callback" in primitives
        state_preserving_required = bool(risk_types & state_preserving_risks)

        if callback_required and shadow_required:
            routes.append("callback_shadow_wrap")
        elif callback_required:
            routes.append("callback_livepatch_wrap")
        if state_preserving_required:
            routes.append("state_preserving_wrap")
        if shadow_required:
            routes.append("shadow_variable_wrap")

        if not routes:
            routes.append("minimal_livepatch_wrap")

        if "minimal_livepatch_wrap" not in routes:
            routes.append("minimal_livepatch_wrap")
        if direct_apply_viable:
            routes.append("direct_apply_patch")

        ordered_routes = list(dict.fromkeys(routes))
        return ordered_routes, ordered_routes[0] if ordered_routes else None
