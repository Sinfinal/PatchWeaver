"""验证编排骨架。"""

from __future__ import annotations

from patchweaver.models.validation import ValidationReport


class Validator:
    """负责组织加载、卸载和冒烟验证。"""

    def empty_report(self) -> ValidationReport:
        """返回一份默认验证报告。"""

        return ValidationReport()

