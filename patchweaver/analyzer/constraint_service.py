"""约束诊断骨架"""

from __future__ import annotations

from patchweaver.models.constraint import ConstraintReport
from patchweaver.models.patch import PatchBundle
from patchweaver.analyzer.risk_rule_registry import RiskRuleRegistry


class ConstraintDiagnoser:
    """负责生成热补丁约束报告"""

    def __init__(self) -> None:
        """初始化风险规则注册表"""

        self.registry = RiskRuleRegistry()

    def diagnose(self, patch_bundle: PatchBundle) -> ConstraintReport:
        """根据补丁内容返回最小约束报告"""

        risk_items = self.registry.evaluate(patch_bundle)
        return ConstraintReport(
            task_id=patch_bundle.task_id,
            risk_items=risk_items,
            high_risk_count=sum(1 for item in risk_items if item.severity == "high"),
            requires_callback=any("callback" in item.required_primitives for item in risk_items),
            requires_shadow_variable=any("shadow_variable" in item.required_primitives for item in risk_items),
            summary="已完成最小约束分析。",
        )
