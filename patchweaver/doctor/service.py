"""环境诊断服务。"""

from __future__ import annotations

from patchweaver.models.doctor import DoctorCheck, DoctorReport


class DoctorService:
    """负责收敛环境检查结果。"""

    def build_report(self, *, runtime: dict[str, str], checks: list[DoctorCheck]) -> DoctorReport:
        """把运行时信息和检查项整理成报告。"""

        summary = {
            "total": len(checks),
            "ok": sum(1 for item in checks if item.ok),
            "warn": sum(1 for item in checks if item.status == "warn"),
            "error": sum(1 for item in checks if item.status == "error"),
        }
        return DoctorReport(runtime=runtime, checks=checks, summary=summary)

