"""环境检查项"""

from __future__ import annotations

from patchweaver.models.doctor import DoctorCheck


def build_check(*, category: str, name: str, label: str, ok: bool, detail: str, status: str | None = None) -> DoctorCheck:
    """构造一条标准化检查结果"""

    return DoctorCheck(
        category=category,
        name=name,
        label=label,
        ok=ok,
        status=status or ("ok" if ok else "warn"),
        detail=detail,
    )
