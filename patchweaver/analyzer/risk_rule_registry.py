"""风险规则注册表。"""

from __future__ import annotations

from patchweaver.models.constraint import RiskItem
from patchweaver.models.patch import PatchBundle


class RiskRuleRegistry:
    """负责提供 MVP 阶段的最小风险规则。"""

    def evaluate(self, patch_bundle: PatchBundle) -> list[RiskItem]:
        """根据补丁信息生成基础风险项。"""

        if patch_bundle.affected_files:
            return [
                RiskItem(
                    risk_type="unknown_patchability",
                    severity="low",
                    evidence=[f"涉及文件: {path}" for path in patch_bundle.affected_files],
                    affected_functions=["example_fix"],
                    required_primitives=["wrapper"],
                )
            ]
        return []

