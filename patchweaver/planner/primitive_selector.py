"""原语选择器。"""

from __future__ import annotations

from patchweaver.models.constraint import ConstraintReport
from patchweaver.planner.primitive_catalog import PrimitiveCatalog


class PrimitiveSelector:
    """负责从原语目录中挑选当前候选。"""

    def __init__(self) -> None:
        """初始化原语目录。"""

        self.catalog = PrimitiveCatalog()

    def select(self, report: ConstraintReport) -> list[str]:
        """返回当前约束下的原语选择结果。"""

        return sorted(dict.fromkeys(self.catalog.suggest(report)))

