"""热补丁原语目录"""

from __future__ import annotations

from patchweaver.models.constraint import ConstraintReport


class PrimitiveCatalog:
    """负责返回当前可用的热补丁原语"""

    def suggest(self, report: ConstraintReport) -> list[str]:
        """根据约束报告给出建议原语"""

        primitives = {"direct_apply"}
        for item in report.risk_items:
            primitives.update(item.required_primitives)
        if report.high_risk_count > 0:
            primitives.add("wrapper")
        return sorted(primitives)

